# Log

Append-only record of operations, oldest first. Header format:
`## [YYYY-MM-DD] <setup|ingest|query|lint|schema|note> | <title>`

## [{{DATE}}] setup | Created {{TITLE}}
- layout: raw/, wiki/{sources,entities,concepts,analyses}, outputs/
- qmd: {{WIKI_COLLECTION}} (wiki/), {{RAW_COLLECTION}} (raw/)
- mode: {{MODE}}
