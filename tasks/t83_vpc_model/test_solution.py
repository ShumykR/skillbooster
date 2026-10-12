import copy

import pytest

from solution import audit_vpc, can_connect, can_reach_internet, reachable_from_internet, subnet_kind


def good_vpc():
    return {
        "cidr": "10.0.0.0/16",
        "internet_gateway": True,
        "subnets": {
            "pub-a": {"cidr": "10.0.1.0/24", "az": "a", "route_table": "rt-public"},
            "pub-b": {"cidr": "10.0.2.0/24", "az": "b", "route_table": "rt-public"},
            "app-a": {"cidr": "10.0.11.0/24", "az": "a", "route_table": "rt-app-a"},
            "app-b": {"cidr": "10.0.12.0/24", "az": "b", "route_table": "rt-app-b"},
            "db-a": {"cidr": "10.0.21.0/24", "az": "a", "route_table": "rt-isolated"},
        },
        "route_tables": {
            "rt-public": [{"dest": "10.0.0.0/16", "target": "local"}, {"dest": "0.0.0.0/0", "target": "igw"}],
            "rt-app-a": [{"dest": "10.0.0.0/16", "target": "local"}, {"dest": "0.0.0.0/0", "target": "nat-a"}],
            "rt-app-b": [{"dest": "10.0.0.0/16", "target": "local"}, {"dest": "0.0.0.0/0", "target": "nat-b"}],
            "rt-isolated": [{"dest": "10.0.0.0/16", "target": "local"}],
        },
        "nat_gateways": {"nat-a": {"subnet": "pub-a"}, "nat-b": {"subnet": "pub-b"}},
        "security_groups": {
            "sg-alb": {"ingress": [{"port": 443, "source": "0.0.0.0/0"}], "egress": [{"port": 8000, "dest": "sg:sg-app"}]},
            "sg-app": {"ingress": [{"port": 8000, "source": "sg:sg-alb"}],
                       "egress": [{"port": 5432, "dest": "sg:sg-db"}, {"port": 443, "dest": "0.0.0.0/0"}]},
            "sg-db": {"ingress": [{"port": 5432, "source": "sg:sg-app"}], "egress": []},
            "sg-open-out": {"ingress": []},
        },
        "instances": {
            "alb": {"subnet": "pub-a", "sgs": ["sg-alb"], "ip": "10.0.1.10", "public_ip": True},
            "app": {"subnet": "app-a", "sgs": ["sg-app"], "ip": "10.0.11.10"},
            "db": {"subnet": "db-a", "sgs": ["sg-db"], "ip": "10.0.21.10", "tier": "db"},
            "bastion": {"subnet": "pub-b", "sgs": ["sg-open-out"], "ip": "10.0.2.5", "public_ip": True},
        },
    }


@pytest.fixture
def vpc():
    return good_vpc()


# ---------- subnet_kind -------------------------------------------------------


def test_subnet_kinds(vpc):
    assert subnet_kind(vpc, "pub-a") == "public"
    assert subnet_kind(vpc, "app-a") == "private"
    assert subnet_kind(vpc, "db-a") == "isolated"


def test_default_route_to_local_or_missing_is_isolated(vpc):
    vpc["route_tables"]["rt-isolated"] = [{"dest": "0.0.0.0/0", "target": "local"}]
    assert subnet_kind(vpc, "db-a") == "isolated"


# ---------- вихід в інтернет --------------------------------------------------


def test_public_instance_with_public_ip_reaches_internet(vpc):
    assert can_reach_internet(vpc, "bastion") is True


def test_public_subnet_without_public_ip_cannot(vpc):
    vpc["instances"]["bastion"]["public_ip"] = False
    assert can_reach_internet(vpc, "bastion") is False


def test_private_instance_reaches_internet_through_nat(vpc):
    assert can_reach_internet(vpc, "app") is True


def test_isolated_instance_cannot(vpc):
    assert can_reach_internet(vpc, "db") is False


def test_nat_in_private_subnet_is_useless(vpc):
    vpc["nat_gateways"]["nat-a"]["subnet"] = "app-b"
    assert can_reach_internet(vpc, "app") is False


def test_no_internet_gateway_means_no_internet(vpc):
    vpc["internet_gateway"] = False
    assert can_reach_internet(vpc, "bastion") is False
    assert can_reach_internet(vpc, "app") is False


def test_egress_rule_can_block_internet(vpc):
    vpc["security_groups"]["sg-app"]["egress"] = [{"port": 5432, "dest": "sg:sg-db"}]
    assert can_reach_internet(vpc, "app") is False


def test_missing_nat_target_is_unreachable(vpc):
    del vpc["nat_gateways"]["nat-a"]
    assert can_reach_internet(vpc, "app") is False


# ---------- доступ ззовні -----------------------------------------------------


def test_alb_is_reachable_on_443_only(vpc):
    assert reachable_from_internet(vpc, "alb", 443) is True
    assert reachable_from_internet(vpc, "alb", 80) is False


def test_private_and_isolated_are_never_reachable(vpc):
    for name in ("app", "db"):
        assert reachable_from_internet(vpc, name, 8000) is False
        assert reachable_from_internet(vpc, name, 5432) is False


def test_public_ip_and_open_sg_are_both_required(vpc):
    vpc["instances"]["alb"]["public_ip"] = False
    assert reachable_from_internet(vpc, "alb", 443) is False
    vpc["instances"]["alb"]["public_ip"] = True
    vpc["security_groups"]["sg-alb"]["ingress"] = [{"port": 443, "source": "10.0.0.0/16"}]
    assert reachable_from_internet(vpc, "alb", 443) is False


def test_port_ranges_and_all(vpc):
    vpc["security_groups"]["sg-alb"]["ingress"] = [{"port": [8000, 8100], "source": "0.0.0.0/0"}]
    assert reachable_from_internet(vpc, "alb", 8050) is True
    assert reachable_from_internet(vpc, "alb", 8101) is False
    vpc["security_groups"]["sg-alb"]["ingress"] = [{"port": "all", "source": "0.0.0.0/0"}]
    assert reachable_from_internet(vpc, "alb", 22) is True


def test_no_internet_gateway_blocks_inbound(vpc):
    vpc["internet_gateway"] = False
    assert reachable_from_internet(vpc, "alb", 443) is False


# ---------- всередині VPC -----------------------------------------------------


def test_three_tier_chain(vpc):
    assert can_connect(vpc, "alb", "app", 8000) is True
    assert can_connect(vpc, "app", "db", 5432) is True


def test_wrong_direction_wrong_port_and_skipping_a_tier(vpc):
    assert can_connect(vpc, "db", "app", 8000) is False
    assert can_connect(vpc, "alb", "app", 22) is False
    assert can_connect(vpc, "alb", "db", 5432) is False, "alb не в sg-app, а db приймає лише від sg-app (і egress alb дозволяє лише 8000)"
    assert can_connect(vpc, "bastion", "db", 5432) is False


def test_cidr_source_in_ingress(vpc):
    vpc["security_groups"]["sg-db"]["ingress"].append({"port": 5432, "source": "10.0.2.0/24"})
    assert can_connect(vpc, "bastion", "db", 5432) is True
    assert can_connect(vpc, "alb", "db", 5432) is False


def test_missing_egress_key_allows_all_but_present_list_restricts(vpc):
    vpc["security_groups"]["sg-open-out"]["ingress"] = [{"port": 22, "source": "0.0.0.0/0"}]
    vpc["instances"]["app"]["sgs"] = ["sg-open-out"]
    assert can_connect(vpc, "bastion", "app", 22) is True
    assert can_connect(vpc, "app", "db", 5432) is False, "sg-open-out без egress, але db не приймає від нього"


def test_empty_egress_list_denies_everything(vpc):
    vpc["security_groups"]["sg-db"]["ingress"].append({"port": 6000, "source": "0.0.0.0/0"})
    assert can_connect(vpc, "db", "app", 8000) is False


def test_egress_of_several_sgs_is_united(vpc):
    vpc["security_groups"]["sg-extra"] = {"ingress": [], "egress": [{"port": 8000, "dest": "10.0.11.0/24"}]}
    vpc["instances"]["alb"]["sgs"] = ["sg-alb", "sg-extra"]
    vpc["security_groups"]["sg-alb"]["egress"] = [{"port": 1, "dest": "10.99.0.0/16"}]
    assert can_connect(vpc, "alb", "app", 8000) is True


def test_multiple_sgs_on_destination_are_united(vpc):
    vpc["security_groups"]["sg-extra"] = {"ingress": [{"port": 9000, "source": "sg:sg-alb"}]}
    vpc["instances"]["app"]["sgs"] = ["sg-app", "sg-extra"]
    vpc["security_groups"]["sg-alb"]["egress"].append({"port": 9000, "dest": "0.0.0.0/0"})
    assert can_connect(vpc, "alb", "app", 9000) is True


# ---------- аудит -------------------------------------------------------------


def test_good_vpc_is_clean(vpc):
    assert audit_vpc(vpc) == []


def test_vpc001_subnet_outside_vpc(vpc):
    vpc["subnets"]["app-a"]["cidr"] = "192.168.1.0/24"
    assert audit_vpc(vpc) == ["VPC001"]


def test_vpc002_overlap(vpc):
    vpc["subnets"]["app-b"]["cidr"] = "10.0.11.128/25"
    assert audit_vpc(vpc) == ["VPC002"]
    vpc2 = good_vpc()
    vpc2["subnets"]["app-b"]["cidr"] = "10.0.0.0/20"  # накриває 10.0.1.0/24 і 10.0.2.0/24
    assert audit_vpc(vpc2) == ["VPC002"]


def test_vpc003_nat_in_private_subnet(vpc):
    vpc["nat_gateways"]["nat-a"]["subnet"] = "app-a"
    assert audit_vpc(vpc) == ["VPC003"]


def test_vpc004_cross_az_nat(vpc):
    vpc["route_tables"]["rt-app-a"][1]["target"] = "nat-b"
    assert audit_vpc(vpc) == ["VPC004"]


@pytest.mark.parametrize("port, expected", [
    (22, ["VPC005"]), (3389, ["VPC005"]), (5432, ["VPC005"]), (6379, ["VPC005"]), ([20, 30], ["VPC005"]), ("all", ["VPC005"]),
    (443, []), (8080, []), ([1000, 1400], []),
])
def test_vpc005_world_open_sensitive_ports(vpc, port, expected):
    vpc["security_groups"]["sg-open-out"]["ingress"] = [{"port": port, "source": "0.0.0.0/0"}]
    assert audit_vpc(vpc) == expected


def test_vpc005_private_source_is_fine(vpc):
    vpc["security_groups"]["sg-open-out"]["ingress"] = [{"port": 22, "source": "10.0.0.0/16"}]
    assert audit_vpc(vpc) == []


def test_vpc006_public_ip_in_private_subnet(vpc):
    vpc["instances"]["app"]["public_ip"] = True
    assert audit_vpc(vpc) == ["VPC006"]


def test_vpc007_database_in_public_subnet(vpc):
    vpc["instances"]["db"]["subnet"] = "pub-a"
    assert audit_vpc(vpc) == ["VPC007"]


def test_vpc008_dangling_targets(vpc):
    vpc["internet_gateway"] = False
    assert audit_vpc(vpc) == ["VPC008"]
    vpc2 = good_vpc()
    del vpc2["nat_gateways"]["nat-b"]
    assert audit_vpc(vpc2) == ["VPC008"]


def test_vpc009_missing_route_table(vpc):
    vpc["subnets"]["db-a"]["route_table"] = "rt-ghost"
    assert audit_vpc(vpc) == ["VPC009"]


def test_audit_collects_and_sorts_codes(vpc):
    vpc["instances"]["app"]["public_ip"] = True
    vpc["instances"]["db"]["subnet"] = "pub-a"
    vpc["security_groups"]["sg-open-out"]["ingress"] = [{"port": 22, "source": "0.0.0.0/0"}]
    assert audit_vpc(vpc) == ["VPC005", "VPC006", "VPC007"]


def test_functions_do_not_modify_the_model(vpc):
    snapshot = copy.deepcopy(vpc)
    audit_vpc(vpc)
    can_connect(vpc, "alb", "app", 8000)
    can_reach_internet(vpc, "app")
    reachable_from_internet(vpc, "alb", 443)
    subnet_kind(vpc, "pub-a")
    assert vpc == snapshot


def test_egress_restriction_blocks_even_when_ingress_allows(vpc):
    assert can_connect(vpc, "app", "db", 5432) is True
    vpc["security_groups"]["sg-app"]["egress"] = [{"port": 443, "dest": "0.0.0.0/0"}]
    assert can_connect(vpc, "app", "db", 5432) is False


def test_range_boundaries_are_inclusive(vpc):
    vpc["security_groups"]["sg-alb"]["ingress"] = [{"port": [8000, 8100], "source": "0.0.0.0/0"}]
    assert reachable_from_internet(vpc, "alb", 8000) is True
    assert reachable_from_internet(vpc, "alb", 8100) is True
    assert reachable_from_internet(vpc, "alb", 7999) is False


def test_one_sg_without_egress_key_opens_egress_for_the_instance(vpc):
    assert can_reach_internet(vpc, "alb") is False, "egress sg-alb лише на 8000 до sg-app"
    vpc["instances"]["alb"]["sgs"] = ["sg-alb", "sg-open-out"]
    assert can_reach_internet(vpc, "alb") is True
