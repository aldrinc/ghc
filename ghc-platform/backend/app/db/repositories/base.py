from sqlalchemy.orm import Session


class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, obj):
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj
