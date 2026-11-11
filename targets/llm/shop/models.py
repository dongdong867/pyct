"""Classes an LLM seed names with "__class__", for the functions of greet.py, which never import
this module. No hint anywhere."""


class Customer:
    def __init__(self, name, age):
        if age < 0:
            raise ValueError("negative age")
        self.name = name
        self.age = age


class Order:
    def __init__(self, customer, total):
        self.customer = customer
        self.total = total


class Desk:
    def __init__(self, owner):
        self.owner = owner

    def serve(self):
        if self.owner.age > 60:
            return "senior"
        return "regular"


class Till:
    def __init__(self, owner):
        self.owner = owner

    def total(self, discount):
        if self.owner == "admin":
            return 0
        if discount > 10:
            return 1
        return 2
