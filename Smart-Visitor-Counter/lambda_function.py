
import json
import boto3
from datetime import datetime, timezone
from uuid import uuid4
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource(
    "dynamodb",
    region_name="us-east-1"
)

table = dynamodb.Table("SmartVisitorCounter")
events_table = dynamodb.Table("CrowdSenseEvents")


def make_response(data, status_code=200):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        },
        "body": json.dumps(data)
    }


def lambda_handler(event, context):
    request_context = event.get("requestContext", {})
    method = request_context.get(
        "http", {}
    ).get("method", "GET")

    path = event.get("rawPath", "")

    # GET: return current visitor count
    if method == "GET" and path.endswith("/visitor-count"):
        result = table.get_item(
            Key={"id": "visitor_count"}
        )
        count = result.get("Item", {}).get("visit_count", 0)
        return make_response({"visitor_count": int(count)})

    # POST: increment count and save an ENTRY event
    elif method == "POST" and path.endswith("/visitor-count"):
        result = table.update_item(
            Key={"id": "visitor_count"},
            UpdateExpression="ADD visit_count :inc",
            ExpressionAttributeValues={":inc": 1},
            ReturnValues="UPDATED_NEW"
        )
        count = int(result["Attributes"]["visit_count"])

        timestamp = datetime.now(timezone.utc)
        event_date = timestamp.strftime("%Y-%m-%d")
        event_time = timestamp.isoformat()

        try:
            events_table.put_item(
                Item={
                    "event_date": event_date,
                    "event_time_id": event_time + "#" + str(uuid4()),
                    "event_type": "ENTRY",
                    "source": "DASHBOARD",
                    "visitor_count": count,
                    "timestamp": event_time
                }
            )
            print("CrowdSense event saved successfully.")
        except Exception as error:
            print("WARNING: Event history could not be saved:", str(error))

        return make_response({"visitor_count": count})

    # GET: return today's recent history (UTC)
    elif method == "GET" and path.endswith("/visitor-history"):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        result = events_table.query(
            KeyConditionExpression=Key("event_date").eq(today),
            ScanIndexForward=False,
            Limit=20
        )

        records = result.get("Items", [])
        history = [
            {
                "event_type": item.get("event_type", "UNKNOWN"),
                "source": item.get("source", "UNKNOWN"),
                "visitor_count": int(item.get("visitor_count", 0)),
                "timestamp": item.get("timestamp", "")
            }
            for item in records
        ]

        return make_response({
            "date": today,
            "count": len(history),
            "history": history
        })

    return make_response({"error": "Route or method not supported"}, 405)
