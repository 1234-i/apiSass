from app.db.session import Base, engine
from app.models import tenant  # noqa: F401


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print('database tables are ready')

if __name__ == '__main__':
    main()
