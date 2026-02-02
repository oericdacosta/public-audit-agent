# SECTION: DEFENSIVE CODING EXAMPLES

**PATTERN 1: ROBUST JSON PARSING (handling dirty data)**
*Problem:* `query_sql` may return JSON strings or Dictionaries depending on the driver state.
*Bad:*

```python
data = query_sql("SELECT * FROM despesas")
for row in data:
    val = row['valor'] # Crash if row is a string!
```

*Good (Defensive):*

```python
import json
data = query_sql("SELECT * FROM despesas")
for row in data:
    # 1. Self-Correction for Data Types
    if isinstance(row, str):
        try:
            row = json.loads(row)
        except:
            continue # Skip corrupted rows

    # 2. Key Verification
    if isinstance(row, dict):
        val = row.get('valor', 0)
        print(val)
```

**PATTERN 2: SQLITE QUOTING (The "Text-Number" Trap)**
*Problem:* In this legacy database, years and codes are TEXT, not INTEGERS.
*Bad:* `WHERE exercicio_orcamento = 2024` (Returns 0 results)
*Good:* `WHERE exercicio_orcamento = '2024'` (Quotes are mandatory)

**PATTERN 3: PUSH-DOWN COMPUTATION**
*Problem:* Fetching all rows to sum in Python is slow and OOM-prone.
*Bad:*

```python
rows = query_sql("SELECT * FROM despesas") # 1M rows load
total = sum(r['val'] for r in rows)
```

*Good:*

```python
# Push aggregation to the DB engine
rows = query_sql("SELECT SUM(valor) as total FROM despesas")
total_val = rows[0]['total']
# NOTE: double braces needed for LangChain prompt escaping
print(f"Total: {{total_val}}")
```

**PATTERN 4: DISCOVERY BEFORE QUERY**
*Problem:* Guessing table names.
*Bad:* `query_sql("SELECT * FROM expenses")` (Table 'expenses' might not exist)
*Good:*

```python
# 1. Search for potential tables
tables = search_definitions("despesa")
print(f"Found candidates: {{tables}}")

# 2. Inspect schema to find correct columns
schema = describe_table("tb_despesas_2024")
print(schema)
# Now I know columns are 'vlr_liquidado' not 'value'
```

**PATTERN 5: SAFE NULL AGGREGATION**
*Problem:* SUM() with NULL values returns NULL, not 0.
*Bad:*

```python
rows = query_sql("SELECT SUM(valor_pago) as total FROM despesas")
total = rows[0]['total']  # Pode ser None!
```

*Good:*

```python
rows = query_sql("SELECT COALESCE(SUM(valor_pago), 0) as total FROM despesas")
total = rows[0]['total']  # Sempre retorna número
```

**PATTERN 6: SAFE DATE RANGE**
*Problem:* BETWEEN is inclusive on both ends, which can cause off-by-one errors.
*Bad:* `WHERE data BETWEEN '2024-01-01' AND '2024-01-31'` (includes 31/01 at 00:00:00)
*Good:*

```python
# Use explicit bounds for date ranges
rows = query_sql("""
    SELECT * FROM licitacoes
    WHERE data_realizacao_licitacao >= '2024-01-01'
      AND data_realizacao_licitacao < '2024-02-01'
    LIMIT 10
""")
```
