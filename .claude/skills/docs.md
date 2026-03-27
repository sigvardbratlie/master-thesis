# Documentation Standards

## Language

All documentation, type hints, docstrings, comments, variable names, and README files **must be written in English** — no exceptions.

## Type Hints

Every function and method must have full type hints on all parameters and the return type.

```python
# Correct
def get_project(project_id: str, user_id: str) -> Project:
    ...

# Wrong — missing hints
def get_project(project_id, user_id):
    ...
```

## Docstrings

Every function and method must have a docstring describing what it does, its parameters, and its return value.

```python
def get_project(project_id: str, user_id: str) -> Project:
    """Fetch a project by ID, scoped to the given user.

    Args:
        project_id: The UUID of the project to retrieve.
        user_id: The UUID of the authenticated user.

    Returns:
        The matching Project instance.

    Raises:
        ValueError: If the project does not exist or the user lacks access.
    """
    ...
```

## Keyword Arguments at Call Sites

All function calls must use explicit keyword arguments. Positional-only calls are not allowed.

```python
# Correct
result = get_project(project_id=project_id, user_id=user_id)

# Wrong — positional arguments
result = get_project(project_id, user_id)
```

This applies to internal helpers, tool calls, and third-party library calls where the API permits keyword arguments.
