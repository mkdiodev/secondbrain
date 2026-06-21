"""Default markdown templates for soul.md, user.md, agent.md."""

SOUL_TEMPLATE = """# Soul

> The persistent essence of this SecondBrain instance.
> Update this file whenever the system's core values, purpose, or identity evolve.

## Purpose

What is this SecondBrain for? Why does it exist?

## Core Values

- Value one
- Value two
- Value three

## Identity

Name, tone, style, and any defining characteristics.

## Principles

Guiding rules that should rarely change.

## Evolution Log

| Date | Change | Reason |
|------|--------|--------|
"""

USER_TEMPLATE = """# User Profile

> Everything known about the human user.
> Keep this updated as preferences, habits, and context are discovered.

## Basics

- **Name:**
- **Timezone:**
- **Preferred language:**

## Preferences

- Communication style:
- Detail level:
- Tools / workflows:

## Goals

Short-term and long-term goals.

## Context

Relevant background: job, projects, relationships, etc.

## History

Important events, decisions, and milestones.

## Notes

Free-form observations.
"""

AGENT_TEMPLATE = """# Agent Profile

> The assistant's own self-model.
> Update when capabilities, responsibilities, or self-knowledge change.

## Role

What is this agent's primary function?

## Capabilities

- Capability one
- Capability two

## Responsibilities

What is the agent accountable for?

## Style

How does the agent communicate and behave?

## Boundaries

What should the agent NOT do?

## Self-Reflection

Observations about past performance and desired improvements.

## Evolution Log

| Date | Change | Reason |
|------|--------|--------|
"""

DAILY_LOG_TEMPLATE = """# Daily Log: {date}

> Auto-generated daily memory file.
> Add entries below or use the API / CLI to append.

"""
