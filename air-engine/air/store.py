"""Storage boundary. InMemoryStore mirrors the DynamoDB tables; a DynamoStore will implement the same API."""

TABLES = ("observations", "quality", "events", "areas", "decisions", "alerts",
          "authorizations", "messages", "deliveries", "audit", "cycles")


class InMemoryStore:
    def __init__(self):
        self.t = {name: {} for name in TABLES}
        self.state = None

    def put(self, table, key, item):
        self.t[table][key] = item
        return item

    def get(self, table, key):
        return self.t[table].get(key)

    def values(self, table):
        return list(self.t[table].values())
