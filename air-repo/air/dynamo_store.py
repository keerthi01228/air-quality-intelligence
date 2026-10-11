"""DynamoDB-backed store: the same API as InMemoryStore, on ONE table.

Table design (create it once in the console):
    table name     : air-data   (or set the TABLE_NAME environment variable)
    partition key  : pk  (String)
    sort key       : sk  (String)
Each AIR record is saved as a JSON string in the 'data' attribute, with pk = "T#<table>" and
sk = the record id. Uses the low-level boto3 client, so it works with plain Lambda.
"""
import json
import os

TABLES = ("observations", "quality", "events", "areas", "decisions", "alerts",
          "authorizations", "messages", "deliveries", "audit", "cycles", "state")


class DynamoStore:
    def __init__(self, client=None, table_name=None):
        if client is None:
            import boto3
            client = boto3.client("dynamodb")
        self.client = client
        self.table_name = table_name or os.environ.get("TABLE_NAME", "air-data")
        self._state = None
        self._loaded = False

    @staticmethod
    def _pk(name):
        return "T#" + name

    def put(self, table, key, item):
        self.client.put_item(TableName=self.table_name, Item={
            "pk": {"S": self._pk(table)}, "sk": {"S": key}, "data": {"S": json.dumps(item)}})
        return item

    def get(self, table, key):
        resp = self.client.get_item(TableName=self.table_name, ConsistentRead=True,
                                    Key={"pk": {"S": self._pk(table)}, "sk": {"S": key}})
        item = resp.get("Item")
        return json.loads(item["data"]["S"]) if item else None

    def _query(self, table):
        items, start = [], None
        while True:
            kwargs = {"TableName": self.table_name, "ConsistentRead": True,
                      "KeyConditionExpression": "pk = :p",
                      "ExpressionAttributeValues": {":p": {"S": self._pk(table)}}}
            if start:
                kwargs["ExclusiveStartKey"] = start
            resp = self.client.query(**kwargs)
            items += resp.get("Items", [])
            start = resp.get("LastEvaluatedKey")
            if not start:
                return items

    def values(self, table):
        return [json.loads(i["data"]["S"]) for i in self._query(table)]

    # engine state (counters, sequences, last readings) lives in one record
    @property
    def state(self):
        if not self._loaded:
            self._state = self.get("state", "main")
            self._loaded = True
        return self._state

    @state.setter
    def state(self, value):
        self._state, self._loaded = value, True
        if value is not None:
            self.put("state", "main", value)

    def save_state(self):
        if self._state is not None:
            self.put("state", "main", self._state)

    def reset(self):
        """Delete every AIR record (demo reset)."""
        for table in TABLES:
            for item in self._query(table):
                self.client.delete_item(TableName=self.table_name,
                                        Key={"pk": item["pk"], "sk": item["sk"]})
        self._state, self._loaded = None, False
