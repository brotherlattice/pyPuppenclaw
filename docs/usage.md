# Usage

The highest-level interface is `PuppenclawService`, which wraps installation, daemon lifecycle, and the typed HTTP client.

```python
from pypuppenclaw import PuppenclawService

service = PuppenclawService()
service.install()

with service.running() as client:
    result = client.site.status(verbose=True)
    print(result.text)
```

You can also work with the lower-level client directly:

```python
from pypuppenclaw import PuppenclawClient

client = PuppenclawClient("http://127.0.0.1:18795")
print(client.health().model_dump())
client.close()
```

For the full public surface, see the API reference pages.
