# 6. Use ORM for managing database connections

Date: 12-2025

## Status

Accepted

## Context

Database connections have to be managed appropriately, to ensure data persistence works for data ingestion.

## Decision

The initial development focused on managing the connections to the database through the code. However, this approach isn't a feasible approach when multiple data sources are feeding data into the dashboard. For efficient connection pooling and central connection management, Object-Relational Mapping (ORM) was chosen for this functionality.  

## Consequences

In Python, [SQLAlchemy][https://www.sqlalchemy.org] provides this functionality through its libraries. The code would be refactored to use the libraries and use it for database connection pooling and management.
