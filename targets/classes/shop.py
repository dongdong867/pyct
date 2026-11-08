"""Classes whose methods run on an instance each input builds through the constructor."""


class Base:
    def describe(self):
        return self.label()


class Cart(Base):
    def __init__(self, owner):
        if owner == "":
            raise ValueError("no owner")
        self.owner = owner

    def total(self, discount):
        if self.owner == "admin":
            return 0
        if discount > 10:
            return discount - 10
        return discount

    def label(self):
        if self.owner == "admin":
            return "staff"
        return "customer"


class Till:
    def __init__(self, owner):
        self.owner = owner

    def total(this, discount):
        if this.owner == "admin":
            return 0
        return discount


class Box:
    def __init__(self, **fields):
        self.fields = fields

    def size(self):
        if self.fields["w"] > 3:
            return 0
        return len(self.fields)


class Member:
    def __init__(self, name, vip=False, tags=None):
        self.name = name
        self.vip = vip
        self.tags = tags

    def price(self):
        if self.vip:
            return 5
        return 10
