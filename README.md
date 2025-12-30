# AI-Powered SEO Workflow

This project is an **AI-assisted SEO application** that transforms Screaming Frog crawl data into review-ready SEO recommendations using large language models, validation logic, and human-in-the-loop approval.

The goal of this project is not to simply generate content with AI, but to demonstrate how AI can be **embedded into a real operational workflow** with guardrails, consistency, and human oversight.

---

## What This App Does

- Ingests Screaming Frog crawl data (CSV)
- Filters to indexable HTML pages with a 200 status code
- Identifies SEO issues such as missing or out-of-range title tags and meta descriptions
- Uses OpenAI GPT-4–class models to generate optimized titles and meta descriptions
- Enforces strict SEO constraints (character limits and formatting rules)
- Validates AI output programmatically and regenerates when constraints are not met
- Requires human review and approval before exporting results

---

## Live Demo

🔗 **Streamlit App:** https://seo-ai-agent-py.streamlit.app/

> Note: A Screaming Frog crawl export and an OpenAI API key are required to use the app.

---

## Technology Stack

- **Language:** Python
- **LLMs:** OpenAI GPT-4–class models (with `gpt-4o-mini` used during development and testing)
- **Data Processing:** pandas
- **UI:** Streamlit
- **Deployment:** Streamlit Community Cloud

---

## Why This Matters

This project reflects a process-first approach to AI:
- AI is used as an assistant, not a replacement for expertise
- Guardrails and validation are enforced programmatically
- Outputs are reviewable, explainable, and scalable

The same architectural approach can be applied to other digital workflows where consistency, quality, and scale are required.

---

## Getting Started Locally

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt

