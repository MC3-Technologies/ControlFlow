import os
from anduril import Lattice

client = Lattice(
    base_url=f"https://{os.getenv('LATTICE_URL')}",
    token=os.getenv('ENVIRONMENT_TOKEN')
)
print(client.entities.get_entity(entity_id="test"))