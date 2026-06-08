# 5. PubMed data cleanup

Date: 2025-12-02

## Status

Accepted

## Context

When the MVP was unveiled at the Plenary-Connect session, the data displayed on the dashboard wasn't matching the live results from the PubMed website. The root cause of this discrepancy is unknown as the web search and API of PubMed returns different result sets. This mismatch can cause significant reputational risk. 

## Decision

To fix the data mismatch, the existing to be cleaned up such that it matches with the live web search results as of the date mentioned in the notebook.

## Consequences

Exact query using the terms "GA4GH" OR "Global Alliance for Genomics and Health" was used to compare the output from the web-search and API response. The results were a match and hence, completely aligned across the platforms. This exercise makes the notebook useful for the community. 
