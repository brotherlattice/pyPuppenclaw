# Usage

```python
from pypuppenclaw import PuppenclawService

service = PuppenclawService()
service.install()

with service.running() as client:
    result = client.site.status(verbose=True)
    print(result.text)
```
