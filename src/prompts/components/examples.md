EXAMPLE OF CORRECT RESPONSE:

```python
import json

# Discover tables
tables = list_tables()
print(f"Tables: {{tables}}")

# Query data
data = query_sql("SELECT * FROM despesas WHERE valor_liquidado > 1000 LIMIT 10")

total = 0
for d in data:
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except:
            pass
    
    if isinstance(d, dict):
        val = d.get('valor_pago', 0)
        if val:
            total += float(val)

print(f"Total spent: {{total}}")
```

EXAMPLE OF METADATA QUESTION:
User: "Qual o nome da tabela de despesas?"

```python
tables = list_tables()
found = None
for t in tables:
    if "despesa" in t.lower():
        found = t
        break

if found:
    print(f"The table name is: {{found}}")
else:
    print("Table not found.")
```
