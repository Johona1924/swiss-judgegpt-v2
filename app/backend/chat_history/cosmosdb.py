import os
import time
from datetime import datetime
from typing import Any, Union

from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.identity.aio import AzureDeveloperCliCredential, ManagedIdentityCredential
from quart import Blueprint, current_app, jsonify, make_response, request

from config import (
    CONFIG_CHAT_HISTORY_COSMOS_ENABLED,
    CONFIG_COSMOS_HISTORY_CLIENT,
    CONFIG_COSMOS_HISTORY_CONTAINER,
    CONFIG_COSMOS_HISTORY_VERSION,
    CONFIG_CREDENTIAL,
)
from decorators import authenticated
from error import error_response

chat_history_cosmosdb_bp = Blueprint("chat_history_cosmos", __name__, static_folder="static")


def current_iso_timestamp():
    """Get current timestamp in ISO format"""
    return datetime.utcnow().isoformat() + "Z"


def iso_to_unix_timestamp(iso_string: str) -> int:
    """Convert ISO datetime string to Unix timestamp in milliseconds"""
    try:
        # Remove the 'Z' suffix and parse the datetime
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return int(dt.timestamp() * 1000)
    except (ValueError, AttributeError):
        # Fallback to current time if parsing fails
        return int(time.time() * 1000)


@chat_history_cosmosdb_bp.post("/chat_history")
@authenticated
async def post_chat_history(auth_claims: dict[str, Any]):
    if not current_app.config[CONFIG_CHAT_HISTORY_COSMOS_ENABLED]:
        return jsonify({"error": "Chat history not enabled"}), 400

    container: ContainerProxy = current_app.config[CONFIG_COSMOS_HISTORY_CONTAINER]
    if not container:
        return jsonify({"error": "Chat history not enabled"}), 400

    entra_oid = auth_claims.get("oid")
    if not entra_oid:
        return jsonify({"error": "User OID not found"}), 401

    try:
        request_json = await request.get_json()
        session_id = request_json.get("id")
        message_pairs = request_json.get("answers")
        first_question = message_pairs[0][0]
        title = first_question + "..." if len(first_question) > 50 else first_question

        # Handle session item timestamps - check if session exists
        session_timestamps = {}
        try:
            existing_session = await container.read_item(item=session_id, partition_key=[entra_oid, session_id])
            # Preserve createdAt, update updatedAt for session activity
            session_timestamps["createdAt"] = existing_session["createdAt"]
            session_timestamps["updatedAt"] = current_iso_timestamp()
        except Exception:
            # New session - set both timestamps
            current_time = current_iso_timestamp()
            session_timestamps["createdAt"] = current_time
            session_timestamps["updatedAt"] = current_time

        # Insert the session item:
        session_item = {
            "id": session_id,
            "version": current_app.config[CONFIG_COSMOS_HISTORY_VERSION],
            "session_id": session_id,
            "entra_oid": entra_oid,  # Keep field name for backward compatibility
            "type": "session",
            "title": title,
            "createdAt": session_timestamps["createdAt"],
            "updatedAt": session_timestamps["updatedAt"],
            "timestamp": iso_to_unix_timestamp(session_timestamps["updatedAt"]),  # For frontend compatibility
        }

        message_pair_items = []
        # Now insert a message item for each question/response pair:
        for ind, message_pair in enumerate(message_pairs):
            message_pair_item = {
                "id": f"{session_id}-{ind}",
                "version": current_app.config[CONFIG_COSMOS_HISTORY_VERSION],
                "session_id": session_id,
                "entra_oid": entra_oid,
                "type": "message_pair",
                "question": message_pair[0],
                "response": message_pair[1],
            }
            
            # Add feedback if it exists in the response
            if isinstance(message_pair[1], dict) and "feedback" in message_pair[1]:
                message_pair_item["feedback"] = message_pair[1]["feedback"]
            else:
                message_pair_item["feedback"] = "neutral"
            
            # Handle message timestamps - check if message exists
            message_id = f"{session_id}-{ind}"
            try:
                existing_message = await container.read_item(item=message_id, partition_key=[entra_oid, session_id])
                # Preserve both timestamps for existing messages
                message_pair_item["createdAt"] = existing_message["createdAt"]
                message_pair_item["updatedAt"] = existing_message["updatedAt"]
            except Exception:
                # New message - set both timestamps
                current_time = current_iso_timestamp()
                message_pair_item["createdAt"] = current_time
                message_pair_item["updatedAt"] = current_time
                
            message_pair_items.append(message_pair_item)

        batch_operations = [("upsert", (session_item,))] + [
            ("upsert", (message_pair_item,)) for message_pair_item in message_pair_items
        ]
        await container.execute_item_batch(batch_operations=batch_operations, partition_key=[entra_oid, session_id])
        return jsonify({}), 201
    except Exception as error:
        return error_response(error, "/chat_history")


@chat_history_cosmosdb_bp.get("/chat_history/sessions")
@authenticated
async def get_chat_history_sessions(auth_claims: dict[str, Any]):
    if not current_app.config[CONFIG_CHAT_HISTORY_COSMOS_ENABLED]:
        return jsonify({"error": "Chat history not enabled"}), 400

    container: ContainerProxy = current_app.config[CONFIG_COSMOS_HISTORY_CONTAINER]
    if not container:
        return jsonify({"error": "Chat history not enabled"}), 400

    entra_oid = auth_claims.get("oid")
    if not entra_oid:
        return jsonify({"error": "User OID not found"}), 401

    try:
        count = int(request.args.get("count", 10))
        continuation_token = request.args.get("continuation_token")

        res = container.query_items(
            query="SELECT c.id, c.entra_oid, c.title, c.timestamp, c.updatedAt, c.createdAt FROM c WHERE c.entra_oid = @entra_oid AND c.type = @type ORDER BY c.timestamp DESC",
            parameters=[dict(name="@entra_oid", value=entra_oid), dict(name="@type", value="session")],
            partition_key=[entra_oid],
            max_item_count=count,
        )

        pager = res.by_page(continuation_token)

        # Get the first page, and the continuation token
        sessions = []
        try:
            page = await pager.__anext__()
            continuation_token = pager.continuation_token  # type: ignore

            # Build response from ordered results
            async for item in page:
                # Use stored timestamp if available, otherwise convert from updatedAt
                timestamp = item.get("timestamp")
                if timestamp is None:
                    timestamp = iso_to_unix_timestamp(item.get("updatedAt", ""))
                
                sessions.append(
                    {
                        "id": item.get("id"),
                        "entra_oid": item.get("entra_oid"),
                        "title": item.get("title", "untitled"),
                        "timestamp": timestamp,
                        "updatedAt": item.get("updatedAt"),
                        "createdAt": item.get("createdAt"),
                    }
                )

        # If there are no more pages, StopAsyncIteration is raised
        except StopAsyncIteration:
            continuation_token = None

        return jsonify({"sessions": sessions, "continuation_token": continuation_token}), 200

    except Exception as error:
        return error_response(error, "/chat_history/sessions")


@chat_history_cosmosdb_bp.get("/chat_history/sessions/<session_id>")
@authenticated
async def get_chat_history_session(auth_claims: dict[str, Any], session_id: str):
    if not current_app.config[CONFIG_CHAT_HISTORY_COSMOS_ENABLED]:
        return jsonify({"error": "Chat history not enabled"}), 400

    container: ContainerProxy = current_app.config[CONFIG_COSMOS_HISTORY_CONTAINER]
    if not container:
        return jsonify({"error": "Chat history not enabled"}), 400

    entra_oid = auth_claims.get("oid")
    if not entra_oid:
        return jsonify({"error": "User OID not found"}), 401

    try:
        res = container.query_items(
            query="SELECT * FROM c WHERE c.session_id = @session_id AND c.type = @type",
            parameters=[dict(name="@session_id", value=session_id), dict(name="@type", value="message_pair")],
            partition_key=[entra_oid, session_id],
        )

        message_pairs = []
        async for page in res.by_page():
            async for item in page:
                # Create response with feedback included
                response_with_feedback = dict(item["response"])  # Ensure proper copying
                response_with_feedback["feedback"] = item.get("feedback", "neutral")
                
                message_pairs.append([item["question"], response_with_feedback])

        return (
            jsonify(
                {
                    "id": session_id,
                    "entra_oid": entra_oid,
                    "answers": message_pairs,
                }
            ),
            200,
        )
    except Exception as error:
        return error_response(error, f"/chat_history/sessions/{session_id}")


@chat_history_cosmosdb_bp.post("/chat_history/message_feedback")
@authenticated
async def update_message_feedback(auth_claims: dict[str, Any]):
    if not current_app.config[CONFIG_CHAT_HISTORY_COSMOS_ENABLED]:
        return jsonify({"error": "Chat history not enabled"}), 400

    container: ContainerProxy = current_app.config[CONFIG_COSMOS_HISTORY_CONTAINER]
    if not container:
        return jsonify({"error": "Chat history not enabled"}), 400

    entra_oid = auth_claims.get("oid")
    if not entra_oid:
        return jsonify({"error": "User OID not found"}), 401

    try:
        request_json = await request.get_json()
        session_id = request_json.get("session_id")
        message_index = request_json.get("message_index")
        feedback = request_json.get("feedback")

        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
        if message_index is None:
            return jsonify({"error": "message_index is required"}), 400
        if not feedback:
            return jsonify({"error": "feedback is required"}), 400

        message_id = f"{session_id}-{message_index}"
        
        # Read the existing message
        message_item = await container.read_item(item=message_id, partition_key=[entra_oid, session_id])
        
        # Update the feedback and updatedAt (preserve createdAt)
        message_item["feedback"] = feedback
        message_item["updatedAt"] = current_iso_timestamp()
        
        # Also update session's updatedAt to reflect recent activity
        try:
            session_item = await container.read_item(item=session_id, partition_key=[entra_oid, session_id])
            session_item["updatedAt"] = current_iso_timestamp()
            session_item["timestamp"] = iso_to_unix_timestamp(session_item["updatedAt"])  # Update timestamp for frontend compatibility
            await container.upsert_item(session_item)
        except Exception:
            # Session update is optional, don't fail if it doesn't work
            pass
        
        # Upsert the updated message
        await container.upsert_item(message_item)

        return jsonify({
            "message": f"Successfully updated message with feedback {feedback}",
            "message_id": message_id,
        }), 200

    except Exception as error:
        return error_response(error, "/chat_history/message_feedback")


@chat_history_cosmosdb_bp.delete("/chat_history/sessions/<session_id>")
@authenticated
async def delete_chat_history_session(auth_claims: dict[str, Any], session_id: str):
    if not current_app.config[CONFIG_CHAT_HISTORY_COSMOS_ENABLED]:
        return jsonify({"error": "Chat history not enabled"}), 400

    container: ContainerProxy = current_app.config[CONFIG_COSMOS_HISTORY_CONTAINER]
    if not container:
        return jsonify({"error": "Chat history not enabled"}), 400

    entra_oid = auth_claims.get("oid")
    if not entra_oid:
        return jsonify({"error": "User OID not found"}), 401

    try:
        res = container.query_items(
            query="SELECT c.id FROM c WHERE c.session_id = @session_id",
            parameters=[dict(name="@session_id", value=session_id)],
            partition_key=[entra_oid, session_id],
        )

        ids_to_delete = []
        async for page in res.by_page():
            async for item in page:
                ids_to_delete.append(item["id"])

        batch_operations = [("delete", (id,)) for id in ids_to_delete]
        await container.execute_item_batch(batch_operations=batch_operations, partition_key=[entra_oid, session_id])
        return await make_response("", 204)
    except Exception as error:
        return error_response(error, f"/chat_history/sessions/{session_id}")


@chat_history_cosmosdb_bp.before_app_serving
async def setup_clients():
    USE_CHAT_HISTORY_COSMOS = os.getenv("USE_CHAT_HISTORY_COSMOS", "").lower() == "true"
    AZURE_COSMOSDB_ACCOUNT = os.getenv("AZURE_COSMOSDB_ACCOUNT")
    AZURE_CHAT_HISTORY_DATABASE = os.getenv("AZURE_CHAT_HISTORY_DATABASE")
    AZURE_CHAT_HISTORY_CONTAINER = os.getenv("AZURE_CHAT_HISTORY_CONTAINER")

    azure_credential: Union[AzureDeveloperCliCredential, ManagedIdentityCredential] = current_app.config[
        CONFIG_CREDENTIAL
    ]

    if USE_CHAT_HISTORY_COSMOS:
        current_app.logger.info("USE_CHAT_HISTORY_COSMOS is true, setting up CosmosDB client")
        if not AZURE_COSMOSDB_ACCOUNT:
            raise ValueError("AZURE_COSMOSDB_ACCOUNT must be set when USE_CHAT_HISTORY_COSMOS is true")
        if not AZURE_CHAT_HISTORY_DATABASE:
            raise ValueError("AZURE_CHAT_HISTORY_DATABASE must be set when USE_CHAT_HISTORY_COSMOS is true")
        if not AZURE_CHAT_HISTORY_CONTAINER:
            raise ValueError("AZURE_CHAT_HISTORY_CONTAINER must be set when USE_CHAT_HISTORY_COSMOS is true")
        cosmos_client = CosmosClient(
            url=f"https://{AZURE_COSMOSDB_ACCOUNT}.documents.azure.com:443/", credential=azure_credential
        )
        cosmos_db = cosmos_client.get_database_client(AZURE_CHAT_HISTORY_DATABASE)
        cosmos_container = cosmos_db.get_container_client(AZURE_CHAT_HISTORY_CONTAINER)

        current_app.config[CONFIG_COSMOS_HISTORY_CLIENT] = cosmos_client
        current_app.config[CONFIG_COSMOS_HISTORY_CONTAINER] = cosmos_container
        current_app.config[CONFIG_COSMOS_HISTORY_VERSION] = os.environ["AZURE_CHAT_HISTORY_VERSION"]


@chat_history_cosmosdb_bp.after_app_serving
async def close_clients():
    if current_app.config.get(CONFIG_COSMOS_HISTORY_CLIENT):
        cosmos_client: CosmosClient = current_app.config[CONFIG_COSMOS_HISTORY_CLIENT]
        await cosmos_client.close()
