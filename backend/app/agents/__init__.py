"""LangGraph-based AI agents running inside Temporal for durable execution.

Architecture:
- Each agent is a LangGraph StateGraph with typed state, tool nodes, and routing.
- Agents run as Temporal Activities (retryable, timeout-bounded, observable).
- The AgentDispatchWorkflow routes inbound messages to the right agent.
- State is checkpointed to PostgreSQL for cross-session conversation continuity.
- All LLM calls go through the LLMRouter for tiered models + cost tracking.

Agents:
- Lead Onboarding: New lead → qualify → photo analysis → estimate → contract
- Customer Engagement: Ongoing conversations, objections, upsells, scheduling
"""
