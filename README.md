# Agentic SDLC Orchestrator & Scalable URL Shortener

An enterprise-grade reference implementation demonstrating an **Agentic Software Engineering System** that transforms natural language software requirements into verified, production-ready engineering outcomes, featuring a scalable URL Shortener service with persistence, analytics, and SRE guardrails.

---

## 1. Executive Summary & Approach

As engineering systems transition toward autonomous workflows, the core challenge lies in **Controlled Autonomy**—balancing automated code generation, multi-step task decomposition, and rigorous SRE validation with human-in-the-loop oversight. 

This system solves the mandatory use case: *"Build a scalable URL shortener service with APIs, persistence, and analytics,"* by executing through an autonomous agentic pipeline:
1. **Requirement Understanding & Normalization:** Parses intent, flags ambiguities, and establishes scope boundaries.
2. **Structured Task Decomposition:** Breaks high-level needs into an ordered Directed Acyclic Graph (DAG) of tasks.
3. **Multi-Step Orchestration & Code Generation:** Executes code creation, schema definitions, and test suites with built-in retry mechanisms and failure recovery.
4. **Validation & SRE Risk Control:** Enforces automated testing, security scanning, collision mitigation, and health checks.

---

## 2. System Architecture Overview

### A. Agentic Workflow Engine Components
* **Intent Analyzer Agent:** Evaluates prompts against domain rules, identifying missing parameters (e.g., expiration time, custom aliases, rate limits).
* **Decomposer & Scheduler:** Generates task sequences with explicit dependency mapping.
* **Code Generator Agent:** Produces modular Python/FastAPI code, SQLAlchemy models, and OpenAPI schemas.
* **Validator & SRE Guardrail Agent:** Runs automated test suites and validates error handling, idempotency, and performance parameters.

### B. URL Shortener Technical Architecture
* **API Layer:** FastAPI framework providing high-performance async REST endpoints, automatic OpenAPI documentation, and input validation via Pydantic.
* **Persistence Layer:** Relational database (SQLite for lightweight testing, PostgreSQL for production scaling) using SQLAlchemy ORM.
* **Hashing & Collision Mitigation:** Base62 encoding algorithm leveraging cryptographic hashing (SHA-256 truncated) with collision retry logic.
* **Analytics Engine:** Real-time tracking of click count, creation timestamp, referrer headers, user-agent parsing, and IP logging.

---

## 3. Setup and Execution Instructions

### Local Execution Steps
1. **Clone or unzip repository & navigate to directory:**
   ```bash
   cd agentic-url-shortener-system
