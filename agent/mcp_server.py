"""
Agora Marketplace MCP Server

Exposes the marketplace as a set of tools any MCP-compatible AI can call.
Claude users get a marketplace client just by adding this to their config.

Claude Desktop config (~/.claude/claude_desktop_config.json):
{
  "mcpServers": {
    "agora": {
      "command": "python",
      "args": ["/path/to/agora/agent/mcp_server.py"],
      "env": {
        "AGORA_API_URL": "https://api.agora.market",
        "AGORA_API_KEY": "your-agent-token"
      }
    }
  }
}

Claude Code config (~/.claude.json):
{
  "mcpServers": {
    "agora": {
      "command": "python",
      "args": ["agent/mcp_server.py"]
    }
  }
}
"""

from __future__ import annotations
import asyncio
import json
import os
from typing import Any

import httpx
import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions

API_URL = os.environ.get("AGORA_API_URL", "http://localhost:8000")
API_KEY = os.environ.get("AGORA_API_KEY", "")

server = Server("agora-marketplace")


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=30,
    )


# ── Tool definitions ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [

        types.Tool(
            name="search_listings",
            description=(
                "Search the Agora marketplace by natural language query. "
                "Understands intent — 'something for my home gym' returns fitness gear. "
                "Use for: find, search, browse, look for items."
            ),
            inputSchema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query":        {"type": "string",  "description": "Natural language description of what you're looking for"},
                    "location":     {"type": "string",  "description": "City or address to search near, e.g. 'Austin, TX'"},
                    "radius_miles": {"type": "number",  "default": 25},
                    "max_price":    {"type": "number",  "description": "Maximum price in USD"},
                    "min_price":    {"type": "number"},
                    "category":     {"type": "string",  "description": "e.g. electronics, clothing, furniture, vehicles"},
                    "condition":    {
                        "type": "array",
                        "items": {"type": "string", "enum": ["new","like_new","good","fair","poor"]},
                        "description": "Filter by condition. Omit for any.",
                    },
                    "limit":        {"type": "integer", "default": 10, "maximum": 50},
                },
            },
        ),

        types.Tool(
            name="get_listing",
            description="Get full details of a specific listing — description, photos, seller info, all attributes.",
            inputSchema={
                "type": "object",
                "required": ["listing_id"],
                "properties": {
                    "listing_id": {"type": "string"},
                },
            },
        ),

        types.Tool(
            name="generate_listing_draft",
            description=(
                "Turn a casual description into a complete, structured listing draft. "
                "Use this BEFORE create_listing when the seller's input is informal. "
                "Example input: 'selling my old Trek bike, barely used, want around $200, in Austin' "
                "Returns a draft to review before posting."
            ),
            inputSchema={
                "type": "object",
                "required": ["description"],
                "properties": {
                    "description": {"type": "string",  "description": "Casual description of the item"},
                    "price_hint":  {"type": "number",  "description": "Price the seller has in mind"},
                    "location":    {"type": "string"},
                    "photo_urls":  {"type": "array", "items": {"type": "string"}},
                },
            },
        ),

        types.Tool(
            name="create_listing",
            description=(
                "Post a new listing to the marketplace. "
                "Call generate_listing_draft first if working from informal input. "
                "min_acceptable_price is private and never shown to buyers."
            ),
            inputSchema={
                "type": "object",
                "required": ["title","description","price","condition","category_id","lat","lng","location_text"],
                "properties": {
                    "title":                  {"type": "string"},
                    "description":            {"type": "string"},
                    "price":                  {"type": "number"},
                    "condition":              {"type": "string", "enum": ["new","like_new","good","fair","poor"]},
                    "category_id":            {"type": "string"},
                    "lat":                    {"type": "number"},
                    "lng":                    {"type": "number"},
                    "location_text":          {"type": "string", "description": "Human-readable location, e.g. 'Austin, TX'"},
                    "attributes":             {"type": "object", "description": "Structured: {brand, model, size, color, year, ...}"},
                    "price_negotiable":       {"type": "boolean", "default": True},
                    "min_acceptable_price":   {"type": "number",  "description": "Private floor price. Agent won't accept offers below this."},
                    "photo_urls":             {"type": "array", "items": {"type": "string"}},
                },
            },
        ),

        types.Tool(
            name="make_offer",
            description=(
                "Make an offer on a listing. The seller or their agent will respond. "
                "Check the listing's price_negotiable field first. "
                "Include a friendly message to increase acceptance rate."
            ),
            inputSchema={
                "type": "object",
                "required": ["listing_id","amount"],
                "properties": {
                    "listing_id": {"type": "string"},
                    "amount":     {"type": "number", "description": "Offer amount in USD"},
                    "message":    {"type": "string", "description": "Message to the seller"},
                },
            },
        ),

        types.Tool(
            name="respond_to_offer",
            description=(
                "Accept, reject, or counter an offer on your listing. "
                "counter requires counter_amount. "
                "Accepting marks the listing as sold."
            ),
            inputSchema={
                "type": "object",
                "required": ["offer_id","action"],
                "properties": {
                    "offer_id":       {"type": "string"},
                    "action":         {"type": "string", "enum": ["accept","reject","counter"]},
                    "counter_amount": {"type": "number"},
                    "message":        {"type": "string"},
                },
            },
        ),

        types.Tool(
            name="send_message",
            description="Send a message to a seller about a specific listing.",
            inputSchema={
                "type": "object",
                "required": ["listing_id","message"],
                "properties": {
                    "listing_id": {"type": "string"},
                    "message":    {"type": "string"},
                },
            },
        ),

        types.Tool(
            name="get_my_listings",
            description="Get all listings posted by the current user.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["active","sold","all"], "default": "active"},
                },
            },
        ),

        types.Tool(
            name="get_my_offers",
            description="Get offers sent or received by the current user.",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["sent","received","all"], "default": "all"},
                },
            },
        ),

    ]


# ── Tool dispatch ─────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    async with _http() as client:
        result = await _dispatch(client, name, arguments)
    return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def _dispatch(client: httpx.AsyncClient, name: str, args: dict) -> Any:
    match name:

        case "search_listings":
            body = {"query": args["query"]}
            if "location" in args:
                # Geocode location string to lat/lng via a simple lookup
                # (in production, call a geocoding API)
                body["location_text"] = args["location"]
            for k in ("radius_miles","max_price","min_price","category","condition","limit"):
                if k in args:
                    body[k] = args[k]
            r = await client.post("/search", json=body)
            r.raise_for_status()
            return r.json()

        case "get_listing":
            r = await client.get(f"/listings/{args['listing_id']}")
            r.raise_for_status()
            return r.json()

        case "generate_listing_draft":
            r = await client.post("/ai/generate", json=args)
            r.raise_for_status()
            return r.json()

        case "create_listing":
            payload = {
                "title":           args["title"],
                "description":     args["description"],
                "price":           args["price"],
                "condition":       args["condition"],
                "category_id":     args["category_id"],
                "location":        {
                    "lat":  args["lat"],
                    "lng":  args["lng"],
                    "text": args["location_text"],
                },
                "attributes":      args.get("attributes", {}),
                "price_negotiable": args.get("price_negotiable", True),
                "min_price":       args.get("min_acceptable_price"),
                "photo_urls":      args.get("photo_urls", []),
                "listed_by":       "agent",
            }
            r = await client.post("/listings", json=payload)
            r.raise_for_status()
            return r.json()

        case "make_offer":
            lid = args.pop("listing_id")
            r = await client.post(f"/listings/{lid}/offers", json={
                "amount":     args["amount"],
                "message":    args.get("message"),
                "offered_by": "agent",
            })
            r.raise_for_status()
            return r.json()

        case "respond_to_offer":
            oid = args.pop("offer_id")
            r = await client.patch(f"/offers/{oid}", json={
                "action":         args["action"],
                "counter_amount": args.get("counter_amount"),
                "message":        args.get("message"),
                "responded_by":   "agent",
            })
            r.raise_for_status()
            return r.json()

        case "send_message":
            lid = args.pop("listing_id")
            r = await client.post(f"/listings/{lid}/messages", json={
                "body":    args["message"],
                "sent_by": "agent",
            })
            r.raise_for_status()
            return r.json()

        case "get_my_listings":
            r = await client.get("/me/listings", params=args)
            r.raise_for_status()
            return r.json()

        case "get_my_offers":
            r = await client.get("/me/offers", params=args)
            r.raise_for_status()
            return r.json()

        case _:
            raise ValueError(f"Unknown tool: {name}")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="agora-marketplace",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
