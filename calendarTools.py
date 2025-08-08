import os
import asyncio
from datetime import datetime, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import Optional
from agents import function_tool


SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = "<calendar_id>"
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"


@function_tool
async def list_calendar_events() -> dict:
    """
    Lists calendar events.

    Args: (none)

    Returns: dict with:
    calendar_id: str
    status: "success" | "error"
    message: str
    events: list[{"start": str, "summary": str, "event_id": str}]
    """

    print("\n[list_calendar_events] Initiating process to list calendar events...")
    creds = None

    if os.path.exists(TOKEN_FILE):
        try:
            creds = await asyncio.to_thread(Credentials.from_authorized_user_file, TOKEN_FILE, SCOPES)
            print(f"[list_calendar_events] Successfully loaded credentials from '{TOKEN_FILE}'.")
        except Exception as e:
            print(f"[list_calendar_events] Error loading credentials from '{TOKEN_FILE}': {e}")
            return {
                "calendar_id": CALENDAR_ID,
                "status": "error",
                "message": f"Error loading token file '{TOKEN_FILE}': {str(e)}",
                "events": []
            }
    else:
        print(f"[list_calendar_events] Token file '{TOKEN_FILE}' not found.")
        return {
            "calendar_id": CALENDAR_ID,
            "status": "error",
            "message": f"Authentication token file '{TOKEN_FILE}' not found. Please ensure it exists.",
            "events": []
        }

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[list_calendar_events] Credentials expired. Attempting to refresh token...")
            try:
                await asyncio.to_thread(creds.refresh, Request())
                print("[list_calendar_events] Credentials refreshed successfully.")
                try:
                    with open(TOKEN_FILE, "w") as token_file_handle:
                        creds_json = await asyncio.to_thread(creds.to_json)
                        await asyncio.to_thread(token_file_handle.write, creds_json)
                    print(f"[list_calendar_events] Updated token saved to '{TOKEN_FILE}'.")
                except Exception as e:
                    print(f"[list_calendar_events] Failed to save refreshed token to '{TOKEN_FILE}': {e}")
            except Exception as e:
                print(f"[list_calendar_events] Error refreshing token: {e}")
                return {
                    "calendar_id": CALENDAR_ID,
                    "status": "error",
                    "message": f"Error refreshing access token: {str(e)}. Manual re-authentication may be required.",
                    "events": []
                }
        else:
            print("[list_calendar_events] Credentials are not valid and cannot be refreshed (e.g., no refresh token).")
            return {
                "calendar_id": CALENDAR_ID,
                "status": "error",
                "message": "Credentials are not valid and cannot be refreshed. Manual re-authentication may be required.",
                "events": []
            }

    try:
        print(f"[list_calendar_events] Building Google Calendar service for calendar: {CALENDAR_ID}")
        service = await asyncio.to_thread(build, "calendar", "v3", credentials=creds)

        now = datetime.now(tz=timezone.utc).isoformat()
        print(f"[list_calendar_events] Fetching upcoming events (max 10) since {now}.")

        def get_events_sync():
            return (
                service.events()
                .list(
                    calendarId=CALENDAR_ID,
                    timeMin=now,
                    maxResults=10,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

        events_result = await asyncio.to_thread(get_events_sync)
        api_events_list = events_result.get("items", [])

        if not api_events_list:
            print(f"[list_calendar_events] No upcoming events found for calendar: {CALENDAR_ID}.")
            return {
                "calendar_id": CALENDAR_ID,
                "status": "success",
                "message": "No upcoming events found.",
                "events": []
            }

        processed_events = []
        print(f"[list_calendar_events] Processing {len(api_events_list)} fetched event(s).")
        for event_item in api_events_list:
            start_time = event_item["start"].get("dateTime", event_item["start"].get("date"))
            summary_text = event_item["summary"]
            event_id = event_item["id"]
            processed_events.append({"start": start_time, "summary": summary_text, "event_id": event_id})
            print(f"  ID: {event_id} - Event: {start_time} - {summary_text}")

        print(f"[list_calendar_events] Successfully processed {len(processed_events)} events.")
        return {
            "calendar_id": CALENDAR_ID,
            "status": "success",
            "message": f"Successfully fetched {len(processed_events)} upcoming events.",
            "events": processed_events
        }

    except HttpError as error:
        print(f"[list_calendar_events] Google API HttpError occurred: {error}")
        return {
            "calendar_id": CALENDAR_ID,
            "status": "error",
            "message": f"A Google API error occurred: {str(error)}",
            "events": []
        }
    except Exception as e:
        print(f"[list_calendar_events] An unexpected error occurred: {type(e).__name__} - {e}")
        return {
            "calendar_id": CALENDAR_ID,
            "status": "error",
            "message": f"An unexpected error of type {type(e).__name__} occurred: {str(e)}",
            "events": []
        }

@function_tool
async def create_calendar_event(
    summary: str,
    start_datetime_str: str,
    end_datetime_str: str,
    event_timezone: str,
    description: str = "",
    location: str = "",
) -> dict:
    """
    Creates a new calendar event.

    Args (required):
    summary: str — short title, e.g. "Lunch with Sam".
    start_datetime_str: str — ISO 8601 datetime, e.g. "2025-08-10T13:00:00".
    end_datetime_str: str — ISO 8601 datetime, e.g. "2025-08-10T14:00:00".
    event_timezone: str — IANA tz, e.g. "America/New_York".

    Args (optional):
    description: Optional[str]
    location: Optional[str]

    Returns: 
    On success: dict with:
    status: "success"
    message: str
    event_link: str
    event_id: str
    On error: dict with:
    status: "error"
    message: str
    """
    print(f"\n[create_calendar_event] Attempting to create event: '{summary}'")
    creds = None

    if os.path.exists(TOKEN_FILE):
        try:
            creds = await asyncio.to_thread(Credentials.from_authorized_user_file, TOKEN_FILE, SCOPES)
        except Exception as e:
            print(f"[create_calendar_event] Error loading token from '{TOKEN_FILE}': {e}")
            return {"status": "error", "message": f"Error loading token: {str(e)}"}
    else:
        print(f"[create_calendar_event] Token file '{TOKEN_FILE}' not found.")
        return {"status": "error", "message": f"Token file '{TOKEN_FILE}' not found."}

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[create_calendar_event] Credentials expired. Attempting to refresh token...")
            try:
                await asyncio.to_thread(creds.refresh, Request())
                with open(TOKEN_FILE, "w") as token_file_handle:
                    creds_json = await asyncio.to_thread(creds.to_json)
                    await asyncio.to_thread(token_file_handle.write, creds_json)
                print(f"[create_calendar_event] Token refreshed and saved to '{TOKEN_FILE}'.")
            except Exception as e:
                print(f"[create_calendar_event] Error refreshing token: {e}")
                return {"status": "error", "message": f"Error refreshing token: {str(e)}"}
        else:
            message = "Credentials are not valid and cannot be refreshed."
            if not creds: message = "Credentials could not be loaded."
            print(f"[create_calendar_event] {message}")
            return {"status": "error", "message": message}

    event_body = {
        'summary': summary,
        'start': {'dateTime': start_datetime_str, 'timeZone': event_timezone},
        'end': {'dateTime': end_datetime_str, 'timeZone': event_timezone},
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 10},
            ],
        },
    }
    if description:
        event_body['description'] = description
    if location:
        event_body['location'] = location

    try:
        service = await asyncio.to_thread(build, "calendar", "v3", credentials=creds)
        print(f"[create_calendar_event] Inserting event into calendar '{CALENDAR_ID}': '{summary}'")

        def insert_event_sync(body_param):
            return service.events().insert(calendarId=CALENDAR_ID, body=body_param).execute()

        created_event = await asyncio.to_thread(insert_event_sync, event_body)
        event_link = created_event.get('htmlLink')
        event_id = created_event.get('id')

        print(f"[create_calendar_event] Event created successfully: {event_link}")
        return {
            "status": "success",
            "message": f"Event '{summary}' created successfully.",
            "event_link": event_link,
            "event_id": event_id
        }
    except HttpError as error:
        error_message = f"Google API Error: {str(error)}"
        print(f"[create_calendar_event] {error_message}")
        return {"status": "error", "message": error_message}
    except Exception as e:
        print(f"[create_calendar_event] An unexpected error occurred: {type(e).__name__} - {e}")
        return {
            "status": "error",
            "message": f"An unexpected error ({type(e).__name__}) occurred: {str(e)}"
        }
    
@function_tool
async def delete_calendar_event(event_id: str) -> dict:
    """
    Deletes an event from the Google Calendar using its event ID.

    Args:
        event_id (str): The ID of the event to delete.
    Returns:
        dict: A dictionary containing the status and message.
    """
    print(f"\n[delete_calendar_event] Attempting to delete event with ID: '{event_id}'")
    creds = None

    if os.path.exists(TOKEN_FILE):
        try:
            creds = await asyncio.to_thread(Credentials.from_authorized_user_file, TOKEN_FILE, SCOPES)
        except Exception as e:
            print(f"[delete_calendar_event] Error loading token from '{TOKEN_FILE}': {e}")
            return {"status": "error", "message": f"Error loading token: {str(e)}"}
    else:
        print(f"[delete_calendar_event] Token file '{TOKEN_FILE}' not found.")
        return {"status": "error", "message": f"Token file '{TOKEN_FILE}' not found."}

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[delete_calendar_event] Credentials expired. Attempting to refresh token...")
            try:
                await asyncio.to_thread(creds.refresh, Request())
                with open(TOKEN_FILE, "w") as token_file_handle:
                    creds_json = await asyncio.to_thread(creds.to_json)
                    await asyncio.to_thread(token_file_handle.write, creds_json)
                print(f"[delete_calendar_event] Token refreshed and saved to '{TOKEN_FILE}'.")
            except Exception as e:
                print(f"[delete_calendar_event] Error refreshing token: {e}")
                return {"status": "error", "message": f"Error refreshing token: {str(e)}"}
        else:
            message = "Credentials are not valid and cannot be refreshed."
            if not creds: message = "Credentials could not be loaded."
            print(f"[delete_calendar_event] {message}")
            return {"status": "error", "message": message}

    try:
        service = await asyncio.to_thread(build, "calendar", "v3", credentials=creds)
        print(f"[delete_calendar_event] Deleting event ID '{event_id}' from calendar '{CALENDAR_ID}'")

        def delete_event_sync(id_of_event_to_delete):
            service.events().delete(calendarId=CALENDAR_ID, eventId=id_of_event_to_delete).execute()

        await asyncio.to_thread(delete_event_sync, event_id)
        
        print(f"[delete_calendar_event] Event ID '{event_id}' deleted successfully.")
        return {
            "status": "success",
            "message": f"Event ID '{event_id}' deleted successfully."
        }
    except HttpError as error:
        error_message = f"Google API Error when deleting event ID '{event_id}': {str(error)}"
        print(f"[delete_calendar_event] {error_message}")
        return {"status": "error", "message": error_message}
    except Exception as e:
        print(f"[delete_calendar_event] An unexpected error occurred while deleting event ID '{event_id}': {type(e).__name__} - {e}")
        return {
            "status": "error",
            "message": f"An unexpected error ({type(e).__name__}) occurred while deleting event ID '{event_id}': {str(e)}"
        }
    