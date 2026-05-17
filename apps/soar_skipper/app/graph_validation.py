from app.models import Playbook


def validate_playbook_for_save(playbook: Playbook) -> list[str]:
    errors: list[str] = []
    if not any(node.type.startswith("trigger.") for node in playbook.nodes):
        errors.append("playbook must include at least one trigger node")
    return errors
