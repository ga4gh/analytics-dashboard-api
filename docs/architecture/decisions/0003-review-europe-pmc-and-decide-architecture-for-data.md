# 3. Review Europe PMC and decide architecture for data

Date: 2025-11-24

## Status

Accepted

## Context

The initial design of the analytics dashboard envisaged Europe PMC (PMC) as the source of all publication and literature data. However, for the MVP version of the project PubMed was used. After the initial unveiling of the MVP at Plenary-Connect Oct 2025 session, the team decided to go back to PMC instead of PubMed. This decision was based on analysing the data including scope and effort estimations for the change. PMC provides richer and expansive data than PubMed which meant evaluating and defining the data retrieval, transformation, and storage scope.

The outcome of the feasibility exercise was shared in the project meeting on 20th November 2025 and the decision was shared on 24th November. During the evaluation phase, three different types of data storage options were looked at, namely. 
a) htting the PMC API endpoint live through the dashboard 
b) storing the API response (XML/JSON) in a database and applying curation on top of it before displaying 
c) curate the response and store the field-values in a database

## Decision

Based on the complexity and efforts required for implementation, the decision was to go with option c i.e. hit the PMC endpoints, retrieve the data, and store the values in relational database on the cloud. This approach provides maintainability, extensibility and robustness to the solution.

## Consequences

This approach results in easier maintenance, extension of the implementation and robustness to integrate more data sources in the future. It aligns to the design utilised for the existing data sources of GitHub and PyPI.
