import psycopg2
from psycopg2.extras import RealDictCursor
import time
import os
from dotenv import load_dotenv

load_dotenv()
from datetime import datetime

from pywebpush import webpush, WebPushException



# Prevent the same medicine from being sent repeatedly
# during the same minute.
sent_reminders = set()



def db_fetchone(conn, query, params=()):
    cursor = conn.cursor()
    cursor.execute(query, params)
    return cursor.fetchone()


def db_fetchall(conn, query, params=()):
    cursor = conn.cursor()
    cursor.execute(query, params)
    return cursor.fetchall()

def get_db():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")
    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)


def check_medicines(vapid_private_key, vapid_claims):

    now = datetime.now()

    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")

    conn = get_db()

    medicines = db_fetchall(conn, 
        """
        SELECT
            id,
            user_id,
            medicine_type,
            strength,
            from_date,
            to_date,
            time
        FROM medicines
        WHERE from_date <= %s
          AND to_date >= %s
          AND time = %s
        """,
        (
            today,
            today,
            current_time
        )
    )

    conn.close()

    for medicine in medicines:

        # Unique ID for this medicine at this particular minute
        reminder_id = (
            medicine["id"],
            today,
            current_time
        )

        # Don't send the same reminder repeatedly
        if reminder_id in sent_reminders:
            continue

        send_medicine_notification(
            medicine,
            vapid_private_key,
            vapid_claims
        )

        sent_reminders.add(reminder_id)


def send_medicine_notification(
    medicine,
    vapid_private_key,
    vapid_claims
):

    conn = get_db()

    subscriptions = db_fetchall(conn, 
        """
        SELECT endpoint, p256dh, auth
        FROM push_subscriptions
        WHERE user_id = %s
        """,
        (
            medicine["user_id"],
        )
    )

    conn.close()

    if not subscriptions:
        print(
            "No notification subscription found for user:",
            medicine["user_id"]
        )
        return

    for subscription in subscriptions:

        push_subscription = {
            "endpoint": subscription["endpoint"],
            "keys": {
                "p256dh": subscription["p256dh"],
                "auth": subscription["auth"]
            }
        }

        # Set the correct strength unit from the medicine type.
        medicine_type = str(medicine["medicine_type"])

        if medicine_type in ("Tablet", "Capsule", "Cream"):
            unit = "mg"
        elif medicine_type in ("Injection", "Syrup"):
            unit = "ml"
        elif medicine_type == "Drops":
            unit = "drops"
        else:
            unit = ""

        notification_data = (
            '{"title":"💊 Medicine Reminder",'
            '"body":"Time to take your '
            + medicine_type
            + ' (' + str(medicine["strength"])
            + (' ' + unit if unit else '')
            + ')!"}'
        )

        try:

            webpush(
                subscription_info=push_subscription,
                data=notification_data,
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims
            )

            print(
                "Medicine notification sent:",
                medicine["medicine_type"],
                medicine["time"]
            )

        except WebPushException as error:

            print(
                "Medicine notification error:",
                error
            )


def start_reminder(vapid_private_key, vapid_claims):

    print("----------------------------------------")
    print(" Medicine Reminder Started")
    print("----------------------------------------")

    while True:

        try:

            check_medicines(
                vapid_private_key,
                vapid_claims
            )

        except Exception as error:

            print(
                "Reminder error:",
                error
            )

        time.sleep(30)