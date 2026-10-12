"""Завдання №83: VPC з нуля: публічні/приватні підмережі, NAT, security groups, route tables.

Мережа в AWS складається з простих правил, і більшість аварій це їхній збіг у невдалій комбінації. Тут VPC описано
словником, а ти реалізуєш відповіді на головні питання: що це за підмережа, хто куди дістанеться, і що в конфігурації не так.

vpc = {
  "cidr": "10.0.0.0/16", "internet_gateway": True,
  "subnets":  {name: {"cidr": "10.0.1.0/24", "az": "a", "route_table": "rt-public"}},
  "route_tables": {name: [{"dest": "0.0.0.0/0", "target": "igw" | "nat-a" | "local"}]},
  "nat_gateways": {"nat-a": {"subnet": "pub-a"}},
  "security_groups": {name: {"ingress": [{"port": 443 | [from, to] | "all", "source": "0.0.0.0/0" | "10.0.0.0/16" | "sg:sg-web"}],
                              "egress": [{"port": ..., "dest": "0.0.0.0/0" | "cidr" | "sg:name"}]}},
  "instances": {name: {"subnet": str, "sgs": [str], "ip": "10.0.1.10", "public_ip": bool (типово False), "tier": "db"|... (необов'язково)}},
}
SG без ключа "egress" має типове правило «дозволити все»; з ключем "egress" дозволено лише перелічене (порожній список
забороняє все). Правила всіх SG одного інстансу обʼєднуються (достатньо одного дозволу), а SG без ключа "egress"
дозволяє все.
Трафік усередині VPC (маршрут `local`) існує завжди; керує ним лише security group.

subnet_kind(vpc, subnet) -> "public" | "private" | "isolated"
    за маршрутом 0.0.0.0/0 у таблиці маршрутів підмережі: на "igw" -> public; на ім'я NAT-шлюзу (ключ nat_gateways) -> private;
    інакше (немає маршруту за замовчуванням або він "local") -> isolated.
can_reach_internet(vpc, instance) -> bool    чи може інстанс ініціювати вихід в інтернет:
    * egress дозволяє 0.0.0.0/0 (будь-який порт: достатньо правила з dest "0.0.0.0/0") або якась SG не має ключа "egress";
    * public-підмережа: потрібні `internet_gateway` True і `public_ip` True;
    * private: NAT-шлюз з маршруту існує, його підмережа public, і `internet_gateway` True; public_ip не потрібен;
    * isolated: False.
reachable_from_internet(vpc, instance, port) -> bool    чи може зовнішній клієнт підʼєднатися на `port`:
    підмережа public, `internet_gateway` True, `public_ip` True і в ingress однієї з SG інстансу є правило з джерелом
    рівно "0.0.0.0/0" і діапазоном, що містить порт ("all" містить усі).
can_connect(vpc, src, dst, port) -> bool    інстанс -> інстанс усередині VPC:
    ingress однієї з SG призначення має правило на `port` із джерелом "sg:<SG>", де <SG> серед SG джерела, або з CIDR, що
    містить "ip" джерела; І egress SG джерела (якщо він заданий хоч у однієї SG джерела; правила різних SG обʼєднуються)
    має правило на `port` з dest "0.0.0.0/0", CIDR, що містить "ip" призначення, або "sg:<SG>" із SG призначення
    (або якась SG джерела не має ключа "egress").
audit_vpc(vpc) -> list[str]    відсортований список унікальних кодів:
    * VPC001  CIDR підмережі не лежить усередині CIDR VPC;
    * VPC002  CIDR двох підмереж перетинаються;
    * VPC003  NAT-шлюз стоїть у підмережі, що не public;
    * VPC004  private-підмережа виходить через NAT з іншої AZ (збій AZ відрізає її; плюс платний міжзонний трафік);
    * VPC005  у SG є ingress з джерелом "0.0.0.0/0" на портах 22 або 3389, або на порту бази даних
              (3306, 5432, 6379, 27017, 1433), у тому числі через діапазон чи "all";
    * VPC006  інстанс у НЕ public-підмережі має public_ip True;
    * VPC007  інстанс із tier "db" стоїть у public-підмережі;
    * VPC008  маршрут веде на неіснуючу ціль: "igw" без `internet_gateway`, або NAT, якого немає в nat_gateways;
    * VPC009  підмережа посилається на неіснуючу таблицю маршрутів.
"""
import ipaddress  # noqa: F401


def subnet_kind(vpc: dict, subnet: str) -> str:
    raise NotImplementedError


def can_reach_internet(vpc: dict, instance: str) -> bool:
    raise NotImplementedError


def reachable_from_internet(vpc: dict, instance: str, port: int) -> bool:
    raise NotImplementedError


def can_connect(vpc: dict, src: str, dst: str, port: int) -> bool:
    raise NotImplementedError


def audit_vpc(vpc: dict) -> list[str]:
    raise NotImplementedError
