"""Hand-written OpenAPI 3.0 spec for the Todo & Notes API.

Served at /api/openapi.json for auto-discovery by integration clients.
"""

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Todo & Notes API",
        "version": "1.0.0",
        "description": "Manage todos, notes, and work items.",
    },
    "paths": {
        "/api/todos": {
            "get": {
                "operationId": "list_todos",
                "summary": "List all todos",
                "responses": {
                    "200": {
                        "description": "Array of todo objects",
                        "content": {"application/json": {"schema": {"type": "array", "items": {"$ref": "#/components/schemas/Todo"}}}},
                    }
                },
            },
            "post": {
                "operationId": "create_todo",
                "summary": "Create a new todo",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/TodoCreate"}
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Created todo",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Todo"}}},
                    }
                },
            },
        },
        "/api/todos/{tid}": {
            "get": {
                "operationId": "get_todo",
                "summary": "Get a single todo by ID",
                "parameters": [{"name": "tid", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {
                    "200": {"description": "Todo object", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Todo"}}}},
                    "404": {"description": "Not found"},
                },
            },
            "put": {
                "operationId": "update_todo",
                "summary": "Update a todo",
                "parameters": [{"name": "tid", "in": "path", "required": True, "schema": {"type": "string"}}],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/TodoUpdate"}}},
                },
                "responses": {
                    "200": {"description": "Updated todo", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Todo"}}}},
                    "404": {"description": "Not found"},
                },
            },
            "delete": {
                "operationId": "delete_todo",
                "summary": "Delete a todo",
                "parameters": [{"name": "tid", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"204": {"description": "Deleted"}, "404": {"description": "Not found"}},
            },
        },
        "/api/todos/{tid}/done": {
            "post": {
                "operationId": "mark_todo_done",
                "summary": "Mark a todo as done",
                "parameters": [{"name": "tid", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {
                    "200": {"description": "Updated todo", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Todo"}}}},
                    "404": {"description": "Not found"},
                },
            }
        },
        "/api/notes": {
            "get": {
                "operationId": "list_notes",
                "summary": "List all notes",
                "responses": {
                    "200": {
                        "description": "Array of note objects",
                        "content": {"application/json": {"schema": {"type": "array", "items": {"$ref": "#/components/schemas/Note"}}}},
                    }
                },
            },
            "post": {
                "operationId": "create_note",
                "summary": "Create a new note",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/NoteCreate"}}},
                },
                "responses": {
                    "201": {"description": "Created note", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Note"}}}},
                },
            },
        },
        "/api/notes/{nid}": {
            "get": {
                "operationId": "get_note",
                "summary": "Get a single note by ID",
                "parameters": [{"name": "nid", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {
                    "200": {"description": "Note object", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Note"}}}},
                    "404": {"description": "Not found"},
                },
            },
            "put": {
                "operationId": "update_note",
                "summary": "Update a note",
                "parameters": [{"name": "nid", "in": "path", "required": True, "schema": {"type": "string"}}],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/NoteUpdate"}}},
                },
                "responses": {
                    "200": {"description": "Updated note", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Note"}}}},
                    "404": {"description": "Not found"},
                },
            },
            "delete": {
                "operationId": "delete_note",
                "summary": "Delete a note",
                "parameters": [{"name": "nid", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"204": {"description": "Deleted"}, "404": {"description": "Not found"}},
            },
        },
        "/api/work": {
            "get": {
                "operationId": "list_work_items",
                "summary": "List all work items",
                "responses": {
                    "200": {
                        "description": "Array of work item objects",
                        "content": {"application/json": {"schema": {"type": "array", "items": {"$ref": "#/components/schemas/WorkItem"}}}},
                    }
                },
            },
            "post": {
                "operationId": "create_work_item",
                "summary": "Create a new work item",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/WorkItemCreate"}}},
                },
                "responses": {
                    "201": {"description": "Created work item", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/WorkItem"}}}},
                },
            },
        },
        "/api/work/{wid}": {
            "get": {
                "operationId": "get_work_item",
                "summary": "Get a single work item by ID",
                "parameters": [{"name": "wid", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {
                    "200": {"description": "Work item object", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/WorkItem"}}}},
                    "404": {"description": "Not found"},
                },
            },
            "put": {
                "operationId": "update_work_item",
                "summary": "Update a work item",
                "parameters": [{"name": "wid", "in": "path", "required": True, "schema": {"type": "string"}}],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/WorkItemUpdate"}}},
                },
                "responses": {
                    "200": {"description": "Updated work item", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/WorkItem"}}}},
                    "404": {"description": "Not found"},
                },
            },
            "delete": {
                "operationId": "delete_work_item",
                "summary": "Delete a work item",
                "parameters": [{"name": "wid", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"204": {"description": "Deleted"}, "404": {"description": "Not found"}},
            },
        },
    },
    "components": {
        "schemas": {
            "Tags": {
                "type": "object",
                "description": "Key-value tags. Must include 'category' (any string) and 'priority' (low|medium|high|urgent).",
                "properties": {
                    "category": {"type": "string", "description": "Category label, e.g. 'work', 'personal', 'shopping'"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                },
                "required": ["category", "priority"],
                "additionalProperties": {"type": "string"},
            },
            "Todo": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string", "nullable": True},
                    "tags": {"$ref": "#/components/schemas/Tags"},
                    "done": {"type": "boolean"},
                    "due_date": {"type": "string", "nullable": True, "description": "YYYY-MM-DD or ISO datetime"},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"},
                },
            },
            "TodoCreate": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "tags": {"$ref": "#/components/schemas/Tags", "description": "Optional. Defaults to category='general', priority='medium' if omitted."},
                    "done": {"type": "boolean", "default": False, "description": "Always set to false when creating new todos."},
                    "due_date": {"type": "string", "description": "YYYY-MM-DD or ISO datetime"},
                },
            },
            "TodoUpdate": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "tags": {"$ref": "#/components/schemas/Tags"},
                    "done": {"type": "boolean"},
                    "due_date": {"type": "string"},
                },
            },
            "Note": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "note": {"type": "string", "nullable": True},
                    "tags": {"$ref": "#/components/schemas/Tags"},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"},
                },
            },
            "NoteCreate": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string"},
                    "note": {"type": "string"},
                    "tags": {"$ref": "#/components/schemas/Tags", "description": "Optional. Defaults to category='general', priority='medium' if omitted."},
                },
            },
            "NoteUpdate": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "note": {"type": "string"},
                    "tags": {"$ref": "#/components/schemas/Tags"},
                },
            },
            "WorkItem": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "nullable": True, "description": "YYYY-MM-DD"},
                    "description": {"type": "string", "nullable": True},
                    "why": {"type": "string", "nullable": True},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"},
                },
            },
            "WorkItemCreate": {
                "type": "object",
                "required": ["name", "start_date"],
                "properties": {
                    "name": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "description": {"type": "string"},
                    "why": {"type": "string"},
                },
            },
            "WorkItemUpdate": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "description": {"type": "string"},
                    "why": {"type": "string"},
                },
            },
        }
    },
}
