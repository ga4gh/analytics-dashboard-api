# Milestones for GA4GH Plenary 2026

We're working towards having four main features ready for **GA4GH Plenary 2026**, which runs from September 28th to October 2nd. Our internal target is to have everything in production by **September 14th** to allow time for final checks before the event.

---

## Primary Features/Add-ons

### 1. Data Provenance

EuropePMC records change without warning — titles get corrected, abstracts revised, and citation counts updated outside our control. Right now we have no way of knowing anything changed until we spot it ourselves, and we can't point to who approved what or when.

**What we're building:**
- A staging layer where all incoming data lands first — nothing reaches the production dashboard until it's been reviewed
- Automatic classification of every ingested record as New, Unchanged, or Changed
- A review queue where curators approve or reject changes with a full field-by-field diff
- Auto-approval for low-risk metric changes (citation counts, availability flags) so the queue stays focused
- A "known divergences" log so rejected changes don't re-surface on every future ingestion
- An audit log in both staging and production — every action on every record is traceable, with before/after state and who did it
- Coverage across all child entities: authors, affiliations, citations, references, fulltexts, and grants

**In scope for plenary:**
- Staging database setup
- Post-ingestion diff and classification service
- Review queue API (approve, reject, export to Excel)
- Promotion service that writes approved records to production
- Audit log in both environments

---

### 2. Persona View

The dashboard currently shows the same view to everyone. A funder, a new visitor, and a software developer all have very different questions — and right now we're not answering any of them particularly well.

**Proposed personas:**

- **Funder** — publications linked to their funded workstreams, geographic spread of research, citation impact over time, which product lines their investment supported
- **Explorer (New Visitor)** — a high-level story of what GA4GH is, growth since 2014, global reach, key numbers; more narrative than data-dense
- **Contributor / Team Member** — GitHub activity across their repos, workstream publication counts, tool adoption, personal contribution footprint
- **Software Developer / Researcher** — repository health per tool, release cadence, open issue trends, cross-links to publications that cite the tool

**In scope for plenary:**
- Persona selector on the dashboard landing page
- Per-persona layout: different widget sets and ordering per audience
- Responsive layouts that work well on presentation displays

---

### 3. Curated GitHub Data _(External dependency - Uncertain scope)_

GA4GH produces a lot of software spread across several GitHub organisations and workstream repos. We've been managing this data manually, which doesn't scale and tends to fall out of date. The plan is to bring repos from organisations like `ga4gh-beacon`, `phenopackets`, `ga4gh-duri`, and others into the GA4GH-managed GitHub instance and ingest them properly.

**What we're building:**
- Automated fetch of repositories from GA4GH-managed and affiliated GitHub organisations
- Per-repo data: description, language, stars, forks, open issues, contributor counts, commit frequency, latest release, archive status
- Workstream tagging — a mapping of each repo to its GA4GH product line
- Dashboard surfaces: browsable tool landscape by workstream, repo health indicators, adoption trends
- Cross-referencing with EPMC data where possible (which publications cite which tools)
- Provenance-backed curation using the same staging/review model as EPMC _(if time permits; otherwise manual curation continues)_

**Things to agree on before we start:**
- Which organisations and repos are in scope
- How to handle repos that span multiple workstreams
- What to do when a repo moves org or gets renamed
- Whether to include third-party implementations of GA4GH standards

**In scope for plenary:**
- Extended GitHub client to fetch across multiple organisations
- Workstream mapping table
- Dashboard additions: repo health cards, workstream tool overview

---

### 4. Separate Staging and Production Instances

We currently have one staging environment (`analytics-staging.ga4gh.org`) but no true production instance — the dashboard and the ingestion pipeline share the same database. Data provenance requires these to be fully separate.

**What we're building:**
- A production environment (`analytics.ga4gh.org`) that contains only curated, approved data
- Fully independent staging and production databases — nothing moves between them without going through the review workflow
- A deployment pipeline that promotes to staging first, then production after validation
- Environment-aware configuration (separate credentials, endpoints, and feature flags per environment)

**In scope for plenary:**
- Production database provisioned
- CloudFormation updated for dual-environment setup
- Independent ECS services for staging and production
- Domain routing and CI/CD pipeline

---

## Other Refinements

- The GA4GH Analytics Dashboard will be clearly branded with GA4GH colours, images, styles, and themes.