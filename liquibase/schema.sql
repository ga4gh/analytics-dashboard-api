CREATE TYPE article_status AS ENUM ('Preprint', 'Published', 'Redacted', 'Unknown');
CREATE TYPE article_type AS ENUM ('Article', 'Grant');
CREATE TYPE contributor_entity_type AS ENUM ('user', 'bot');
CREATE TYPE keyword_source AS ENUM ('github', 'pubmed', 'pypi');
CREATE TYPE product_type AS ENUM ('standard', 'implementation', 'reference');
CREATE TYPE record_status AS ENUM ('Pending', 'Approved', 'Rejected', 'Updated');
CREATE TYPE record_type AS ENUM ('Article', 'Grant', 'Repo', 'Library');
CREATE TYPE repo_action_type AS ENUM ('star', 'watch', 'collaborator');
CREATE TYPE source AS ENUM ('PubMed', 'Europe_PMC', 'Github', 'PyPi');
