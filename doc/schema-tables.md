# Database Table Schemas

Generated from `liquibase/dbchangelog.xml` — CREATE TABLE statements only.
Liquibase internal tables (`databasechangelog`, `databasechangeloglock`) are appended at the end.

Type legend: `int` = INTEGER/BIGINT, `string` = VARCHAR/TEXT, `bool` = BOOLEAN,
`timestamp` = TIMESTAMP (any timezone variant), `jsonb` = JSONB, `uuid` = UUID,
`date` = DATE, `int[]` = INT4[], `jsonb[]` = JSONB[], `string[]` = VARCHAR[],
`string(enum)` = custom PostgreSQL enum type.

---

## Core Tables

```
AFFILIATIONS {
    int         **id**
    int         author_id
    string      institute
    string      location
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

PYPI {
    int         **id**
    int         record_id
    string      project_name
    string      description
    jsonb       download_history
    string      package_url
    string      project_url
    string      release_url
    string      github_url
    string      author_name
    string      author_email
    string      package_version
    bool        is_latest
    string      category
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

PYPI_VERSIONS {
    int         **id**
    string      **package_version**
    string      python_version
    timestamp   release_date
    string      download_url
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

GITHUB_REPOS {
    int         **id**
    int         record_id
    string      name
    string      repo_link
    string      owner
    string      description
    bool        is_fork
    timestamp   last_updated
    timestamp   pushed_at
    bool        is_archived
    string      license
    int         stargazers_count
    int         watchers_count
    int         forks_count
    int         open_issues_count
    int         network_count
    int         subscribers_count
    int         branches_count
    string      created_on
    string      type
    bool        display_flag
    bool        mark_for_archiving
    string      workstream
    string      status
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

GITHUB_ARCHIEVED_STATS {
    int         **id**
    int         repo_id
    int         weekly_commit_add
    int         weekly_commit_del
    int[]       yearly_commit_count
    int         daily_clone_count
    int         daily_view_count
    jsonb[]     last_14_day_top_referral_sources
    jsonb[]     last_14_day_top_referral_path
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

PMC_ARTICLES {
    int         **id**
    int         record_id
    string      source
    string      pm_id
    string      pmc_id
    string      full_text_id
    string      doi
    string      title
    int         pub_year
    string      abstract_text
    string      affiliation
    string      publication_status
    string      language
    jsonb       pub_type
    string      is_open_access
    string      inepmc
    string      inpmc
    string      has_pdf
    string      has_book
    string      has_suppl
    int         cited_by_count
    string      has_references
    timestamp   date_of_creation
    timestamp   first_index_date
    timestamp   fulltext_receive_date
    timestamp   revision_date
    timestamp   epub_date
    timestamp   first_publication_date
    int         ingestion_id
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

PMC_AUTHORS {
    int         **id**
    string      fullname
    string      firstname
    string      lastname
    string      initials
    string      orcid
    int         ingestion_id
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

PMC_AFFILIATIONS {
    int         **id**
    int         author_id
    int         article_id
    string      org_name
    int         affiliation_order
    int         ingestion_id
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

ARTICLES_AUTHORS {
    int         **id**
    int         article_id
    int         author_id
    int         author_order
    int         ingestion_id
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

GRANTS {
    int         **id**
    int         record_id
    string      grant_id
    string      agency
    string      family_name
    string      given_name
    jsonb       alias
    string      funder_name
    string      orcid
    string      doi
    string      title
    date        start_date
    date        end_date
    string      institution_name
    string      initials
    jsonb       abstract
    int         ingestion_id
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

FULLTEXTS {
    int         **id**
    int         article_id
    string      availability
    string      availability_code
    string      document_style
    string      site
    string      url
    int         ingestion_id
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

CITATIONS {
    int         **id**
    int         article_id
    string      citation_id
    string      source
    string      citation_type
    string      title
    string      authors
    int         pub_year
    int         citation_count
    int         ingestion_id
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

PMC_REFERENCES {
    int         **id**
    int         article_id
    string      reference_id
    string      source
    string      citation_type
    string      title
    string      authors
    int         pub_year
    string      issn
    string      essn
    int         cited_order
    string      match
    int         ingestion_id
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

INGESTION {
    int         **id**
    int         version
    timestamp   ingested_at
    string      created_by
    timestamp   created_at
    int         rows_count
}

RECORDS {
    int         **id**
    string(enum) record_type
    string(enum) source
    string(enum) status
    string[]    keyword
    string(enum) product_line
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

ARTICLES {
    int         **id**
    int         record_id
    string      abstract
    string      title
    string      journal
    string      source_id
    string      doi
    string(enum) status
    timestamp   publish_date
    string      link
    int         publication_year
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

AUTHORS {
    int         **id**
    string      name
    string      contact
    bool        is_primary
    string(enum) article_type
    int         article_id
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

REPO_ENTITY_ACTIONS {
    int         **id**
    int         repo_id
    string(enum) action_type
    int         user_id
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

CONTRIBUTOR_ENTITY {
    uuid        **id**
    string      name
    string      user_id
    string      company
    string      email
    string      location
    string(enum) type
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

KEYWORDS {
    int         **id**
    string      name
    string      acronym
    string(enum) source
    string      created_by
    timestamp   created_at
    string      updated_by
    timestamp   updated_at
    string      deleted_by
    timestamp   deleted_at
    int         version
}

SCHEMA_MIGRATIONS {
    int         **version**
    bool        dirty
}
```

---

## Audit Tables

Each audit table captures a before/after snapshot for every INSERT, UPDATE, and DELETE on its parent table.

```
AFFILIATIONS_AUDIT {
    int         **audit_id**
    timestamp   action_tstamp
    string      action
    string      action_by
    int         affiliation_id
    int         author_id_before
    int         author_id_after
    string      institute_before
    string      institute_after
    string      location_before
    string      location_after
    string      created_by_before
    string      created_by_after
    timestamp   created_at_before
    timestamp   created_at_after
    string      updated_by_before
    string      updated_by_after
    timestamp   updated_at_before
    timestamp   updated_at_after
    string      deleted_by_before
    string      deleted_by_after
    timestamp   deleted_at_before
    timestamp   deleted_at_after
    int         version_before
    int         version_after
}

PYPI_AUDIT {
    int         **audit_id**
    timestamp   action_tstamp
    string      action
    string      action_by
    int         pypi_id
    int         record_id_before
    int         record_id_after
    string      project_name_before
    string      project_name_after
    string      description_before
    string      description_after
    jsonb       download_history_before
    jsonb       download_history_after
    string      package_url_before
    string      package_url_after
    string      project_url_before
    string      project_url_after
    string      release_url_before
    string      release_url_after
    string      github_url_before
    string      github_url_after
    string      author_name_before
    string      author_name_after
    string      author_email_before
    string      author_email_after
    string      package_version_before
    string      package_version_after
    bool        is_latest_before
    bool        is_latest_after
    string      created_by_before
    string      created_by_after
    timestamp   created_at_before
    timestamp   created_at_after
    string      updated_by_before
    string      updated_by_after
    timestamp   updated_at_before
    timestamp   updated_at_after
    string      deleted_by_before
    string      deleted_by_after
    timestamp   deleted_at_before
    timestamp   deleted_at_after
    int         version_before
    int         version_after
}

PYPI_VERSIONS_AUDIT {
    int         **audit_id**
    timestamp   action_tstamp
    string      action
    string      action_by
    int         pypi_versions_id
    string      python_version_before
    string      python_version_after
    string      package_version_before
    string      package_version_after
    timestamp   release_date_before
    timestamp   release_date_after
    string      download_url_before
    string      download_url_after
    string      created_by_before
    string      created_by_after
    timestamp   created_at_before
    timestamp   created_at_after
    string      updated_by_before
    string      updated_by_after
    timestamp   updated_at_before
    timestamp   updated_at_after
    string      deleted_by_before
    string      deleted_by_after
    timestamp   deleted_at_before
    timestamp   deleted_at_after
    int         version_before
    int         version_after
}

GITHUB_REPOS_AUDIT {
    int         **audit_id**
    timestamp   action_tstamp
    string      action
    string      action_by
    int         github_repo_id
    string      name_before
    string      name_after
    string      repo_link_before
    string      repo_link_after
    string      owner_before
    string      owner_after
    string      description_before
    string      description_after
    bool        is_fork_before
    bool        is_fork_after
    timestamp   last_updated_before
    timestamp   last_updated_after
    timestamp   pushed_at_before
    timestamp   pushed_at_after
    bool        is_archived_before
    bool        is_archived_after
    string      license_before
    string      license_after
    int         stargazers_count_before
    int         stargazers_count_after
    int         watchers_count_before
    int         watchers_count_after
    int         forks_count_before
    int         forks_count_after
    int         open_issues_count_before
    int         open_issues_count_after
    int         network_count_before
    int         network_count_after
    int         subscribers_count_before
    int         subscribers_count_after
    int         branches_count_before
    int         branches_count_after
    string      created_on_before
    string      created_on_after
    string      created_by_before
    string      created_by_after
    timestamp   created_at_before
    timestamp   created_at_after
    string      updated_by_before
    string      updated_by_after
    timestamp   updated_at_before
    timestamp   updated_at_after
    string      deleted_by_before
    string      deleted_by_after
    timestamp   deleted_at_before
    timestamp   deleted_at_after
    int         version_before
    int         version_after
}

REPO_ENTITY_ACTIONS_AUDIT {
    int         **audit_id**
    timestamp   action_tstamp
    string      action
    string      action_by
    int         repo_entity_actions_id
    string      repo_id_before
    string      repo_id_after
    string      action_type_before
    string      action_type_after
    string      user_id_before
    string      user_id_after
    timestamp   updated_at_before
    timestamp   updated_at_after
    string      updated_by_before
    string      updated_by_after
    timestamp   deleted_at_before
    timestamp   deleted_at_after
    string      deleted_by_before
    string      deleted_by_after
    int         version_before
    int         version_after
}

GITHUB_ARCHIEVED_STATS_AUDIT {
    int         **audit_id**
    timestamp   action_tstamp
    string      action
    string      action_by
    uuid        github_archieved_stats_id
    int         weekly_commit_add_before
    int         weekly_commit_add_after
    int         weekly_commit_del_before
    int         weekly_commit_del_after
    int[]       yearly_commit_count_before
    int[]       yearly_commit_count_after
    int         daily_clone_count_before
    int         daily_clone_count_after
    int         daily_view_count_before
    int         daily_view_count_after
    jsonb[]     last_14_day_top_referral_sources_before
    jsonb[]     last_14_day_top_referral_sources_after
    jsonb[]     last_14_day_top_referral_path_before
    jsonb[]     last_14_day_top_referral_path_after
    string      created_by_before
    string      created_by_after
    timestamp   created_at_before
    timestamp   created_at_after
    string      updated_by_before
    string      updated_by_after
    timestamp   updated_at_before
    timestamp   updated_at_after
    string      deleted_by_before
    string      deleted_by_after
    timestamp   deleted_at_before
    timestamp   deleted_at_after
    int         version_before
    int         version_after
}

KEYWORDS_AUDIT {
    int         **audit_id**
    timestamp   action_tstamp
    string      action
    string      action_by
    int         keywords_id
    string      name_before
    string      name_after
    string      acronym_before
    string      acronym_after
    string      source_before
    string      source_after
    string      created_by_before
    string      created_by_after
    timestamp   created_at_before
    timestamp   created_at_after
    string      updated_by_before
    string      updated_by_after
    timestamp   updated_at_before
    timestamp   updated_at_after
    string      deleted_by_before
    string      deleted_by_after
    timestamp   deleted_at_before
    timestamp   deleted_at_after
    int         version_before
    int         version_after
}

RECORDS_AUDIT {
    int         **audit_id**
    timestamp   action_tstamp
    string      action
    string      action_by
    int         record_id
    string(enum) record_type_before
    string(enum) record_type_after
    string(enum) source_before
    string(enum) source_after
    string(enum) status_before
    string(enum) status_after
    string      created_by_before
    string      created_by_after
    timestamp   created_at_before
    timestamp   created_at_after
    string      updated_by_before
    string      updated_by_after
    timestamp   updated_at_before
    timestamp   updated_at_after
    string      deleted_by_before
    string      deleted_by_after
    timestamp   deleted_at_before
    timestamp   deleted_at_after
    int         version_before
    int         version_after
    string[]    keyword_before
    string[]    keyword_after
    string(enum) product_line_before
    string(enum) product_line_after
}

ARTICLES_AUDIT {
    int         **audit_id**
    timestamp   action_tstamp
    string      action
    string      action_by
    int         article_id
    int         record_id_before
    int         record_id_after
    string      abstract_before
    string      abstract_after
    string      source_id_before
    string      source_id_after
    string      doi_before
    string      doi_after
    string(enum) status_before
    string(enum) status_after
    timestamp   publish_date_before
    timestamp   publish_date_after
    string      link_before
    string      link_after
    string      created_by_before
    string      created_by_after
    timestamp   created_at_before
    timestamp   created_at_after
    string      updated_by_before
    string      updated_by_after
    timestamp   updated_at_before
    timestamp   updated_at_after
    string      deleted_by_before
    string      deleted_by_after
    timestamp   deleted_at_before
    timestamp   deleted_at_after
    int         version_before
    int         version_after
}

AUTHORS_AUDIT {
    int         **audit_id**
    timestamp   action_tstamp
    string      action
    string      action_by
    int         author_id
    string      name_before
    string      name_after
    string      contact_before
    string      contact_after
    bool        is_primary_before
    bool        is_primary_after
    string(enum) article_type_before
    string(enum) article_type_after
    int         article_id_before
    int         article_id_after
    string      created_by_before
    string      created_by_after
    timestamp   created_at_before
    timestamp   created_at_after
    string      updated_by_before
    string      updated_by_after
    timestamp   updated_at_before
    timestamp   updated_at_after
    string      deleted_by_before
    string      deleted_by_after
    timestamp   deleted_at_before
    timestamp   deleted_at_after
    int         version_before
    int         version_after
}

CONTRIBUTOR_ENTITY_AUDIT {
    int         **audit_id**
    timestamp   action_tstamp
    string      action
    string      action_by
    int         contributor_entity_id
    string      name_before
    string      name_after
    string      user_id_before
    string      user_id_after
    string      company_before
    string      company_after
    string      email_before
    string      email_after
    string      location_before
    string      location_after
    string(enum) type_before
    string(enum) type_after
    timestamp   updated_at_before
    timestamp   updated_at_after
    string      updated_by_before
    string      updated_by_after
    timestamp   deleted_at_before
    timestamp   deleted_at_after
    string      deleted_by_before
    string      deleted_by_after
    int         version_before
    int         version_after
}
```

---

## Liquibase Internal Tables

Auto-created by Liquibase at runtime. Not defined in `dbchangelog.xml`.

```
DATABASECHANGELOG {
    string      **id**
    string      **author**
    string      **filename**
    timestamp   dateexecuted
    int         orderexecuted
    string      exectype
    string      md5sum
    string      description
    string      comments
    string      tag
    string      liquibase
    string      contexts
    string      labels
    string      deployment_id
}

DATABASECHANGELOGLOCK {
    int         **id**
    bool        locked
    timestamp   lockgranted
    string      lockedby
}
```

---

## Notes

- `PYPI_VERSIONS` has a composite PK: `(id, package_version)`. The `id` column is also the FK into `pypi`.
- `CONTRIBUTOR_ENTITY.id` is `uuid` — the only non-integer PK in the schema.
- `GITHUB_ARCHIEVED_STATS` — table name has a typo (`archieved` vs `archived`) in the original migration.
- `ARTICLES.publication_year` — original column name in the DB is `"Publication Year"` (with space and capital).
- `INGESTION` has no `updated_*` or `deleted_*` columns — it is append-only.
- `DATABASECHANGELOG` has a composite PK on `(id, author, filename)`.
- `string(enum)` columns use custom PostgreSQL enum types: `RECORD_TYPE`, `SOURCE`, `RECORD_STATUS`, `PRODUCT_TYPE`, `ARTICLE_STATUS`, `ARTICLE_TYPE`, `REPO_ACTION_TYPE`, `CONTRIBUTOR_ENTITY_TYPE`, `KEYWORD_SOURCE`.
