"""Entry point for NAT component discovery.

Importing each tool module triggers its ``@register_function`` decorator so
the orchestrator's three tools (``plan_query``, ``collect_evidence``,
``write_report``) become available to any workflow that references them by
name in config.yml — in particular the ``react_agent`` workflow that the
orchestrator agent runs.
"""

from nat_orchestrator import tool_collect_evidence  # noqa: F401
from nat_orchestrator import tool_plan_query  # noqa: F401
from nat_orchestrator import tool_write_report  # noqa: F401
