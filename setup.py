from setuptools import setup, find_packages

setup(
    name="neutrino-database",
    version="0.1.0",
    description="Shared database models and migrations for Neutrino services",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "sqlalchemy~=2.0.44",
        "alembic==1.17.0",
        "psycopg2-binary==2.9.11",
        "pydantic-settings~=2.11.0",
    ],
    python_requires=">=3.10",
)