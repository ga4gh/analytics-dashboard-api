FROM liquibase/liquibase:4.33.0

COPY dbchangelog.xml .
COPY schema.sql .

CMD ["liquibase", "--changelog-file=dbchangelog.xml", "update"]