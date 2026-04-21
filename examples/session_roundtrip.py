from pypuppenclaw import PuppenclawService
from pypuppenclaw.models import SendSessionRequest, StartSessionRequest

service = PuppenclawService()
service.install()

with service.running() as client:
    client.sessions.start(
        StartSessionRequest(
            agent="codex",
            name="demo",
            directory=".",
            task="Inspect the repo and summarize the build commands.",
        )
    )
    reply = client.sessions.send(
        SendSessionRequest(name="demo", message="Now propose the next step.")
    )
    print(reply.text)
