from pypuppenclaw import PuppenclawService

service = PuppenclawService()
service.install()

with service.running() as client:
    print(client.health().model_dump())
