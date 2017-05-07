NAMESPACED_STATIC_DIRS = {
    "workflow": ["vulcanworkflow:base/static"]
}

WORKFLOW_TOOL_SPEC = {
    "wfhome": {
        "app_path": "vulcanworkflow.tools.wfhome.app:WorkflowHomeApp",
        "installable": False,
        "required": True
    }
}
