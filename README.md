<a name="top"></a>
[![GA4GH Analytics Dashboard](https://www.ga4gh.org/wp-content/themes/ga4gh/dist/assets/svg/logos/logo-full-color.svg)](https://ga4gh.org/)


# GA4GH Analytics Dashboard 
![](https://img.shields.io/badge/license-Apache%202-blue.svg)
![GitHub Actions](https://img.shields.io/badge/github%20actions-%232671E5.svg)
[![Static Badge](https://img.shields.io/badge/language-Python-orange)](https://python.org)
![Static Badge](https://img.shields.io/badge/language-Jupyter_notebooks-red)
[![GitHub release](https://img.shields.io/github/v/release/ga4gh/analytics-dashboard)](#)
![GitHub Release Date](https://img.shields.io/github/release-date/ga4gh/analytics-dashboard)




> # An Analytics Dashboard for Everything GA4GH

⭐ Star us on GitHub — your support motivates the community!

## Table of Contents

- [Overview](#overview)
- [Getting Started](#getting-started)
- [Usage](#usage)
- [Decisions](#decisions)
- [Releases](#releases)
- [Contribute](#contribute)
- [License](#license)
- [Contacts](#contacts)

---

## 🚀 Overview
Analytics are important for standards organisations like GA4GH as it helps to make data-driven decisions. The GA4GH Tech Team is building an analytics dashboard to enable our community to quantify the impact of standards, policy frameworks and products that have been actively developed over the last 12 years. The ability to make data-driven decisions will enable GA4GH to deploy implementation-focussed resources where they are needed most, and identify opportunities for impact - furthering our ambition of facilitating responsible, voluntary, and secure use of genomic and health data. To understand the power of these contributions, the dashboard will be a one-stop exhibit of the GA4GH impact. Data sourced from, for example PubMed, PyPI, GitHub, etc., will be displayed in a user-friendly graphical interface. 

Collaborators across Work Streams can use this to understand how their contributions advance genomic data sharing in a diverse world, gather intelligence to guide future product development, and identify implementation opportunities. 

Sources (will expand):
- GitHub
- PyPI
- PubMed

### 📄 Key Documents

- [Plenary 2026 Milestones](doc/14_plenary_milestones.md): Features planned for GA4GH Plenary 2026 (Sept 28 – Oct 2)
- [Data Provenance Design](doc/epmc-data-provenance-plan.md): Architecture and curation plan for EuropePMC data provenance
- [Provenance Table Schema](doc/provenance-tables.md): Database schema for all provenance, review queue, and audit log tables
- [ER Diagram](doc/er-diagram.md): Entity-relationship diagram for the analytics database
- [Architecture Decisions](doc/architecture/decisions/): ADR log — key architectural decisions and their context

--- 

## 📚 Getting Started
The dashboard is currently in the form of Jupyter notebooks. The notebook can be accessed [here](https://github.com/ga4gh/analytics-dashboard/blob/main/notebooks/Analytics_Dashboard.ipynb). It would be helpful if you have a GitHub ID although, this project is open access so ID isn't mandatory. The notebook runs on most of the user system platforms such as Windows, Mac, Linux, etc. The notebook also takes care of the libraries necessary to run the data visualisation. In the notebook, you can modify visualization types, styling, and data presented. However, note that this requires knowledge of Plotly and Dash libraries. 

> [!IMPORTANT]
> **Data in this current notebook version were last fetched between 1st October (GitHub and PyPi) and 1st December (PubMed) 2025.**

In case you encounter issues in accessing the notebook or running it, please raise it with the team as detailed in the [contribute](#contribute) section.  

---

## 📝 Usage

To run the Notebook on Google Colab (no installation required) 

>[!TIP]
>A GitHub account and authorisation shared with Colab would be required

- Click the "**Open in Colab**" button at the very top of this notebook
- Click "**Run All**" to execute the full notebook end to end
- Wait for results as it might take a couple of minutes for the notebook to fetch the data and create the analytics
- Scroll through the results - Each section provides different insights

  
---

## 🎓 Decisions

An **architecture decision record (ADR)** is a document that captures an important architectural decision made along with its context and consequences. As the dashboard will continue to develop as a community product, all key architectural decisions must be recorded for easy reference. This is a component of **architecture knowledge management (AKM)**. 

ADRs could _possibly_ being synced with feature requests and pull requests (PR). 

All the key decisions are available [here](https://github.com/ga4gh/analytics-dashboard/tree/main/doc/architecture/decisions). 

---

## ✨ Releases 

**[v0.2.0](https://github.com/ga4gh/analytics-dashboard/releases/tag/v0.2.0)**
- API Endpoints to fetch data from PubMed and Github to store into Analytics Dashboard DB.
- API Endpoints to expose data from Analytics Dashboard to Notebooks for visualizations.
- Separate jupyter notebooks to create visualization from PubMed, GitHub and PyPi hosted on Colab.
- Single notebook which displays visualization from all three sources combined.
- Unittest which verified that the data is tested and curated.

---

## 🤝 Contribute
We've made every effort to implement all the main aspects of the data from the sources in the best possible way. However, the development journey doesn't end here, and your input is crucial for our continuous improvement.

> [!IMPORTANT]
> We welcome your ideas, feedback and comments to improve the dashboard! Whether you have feedback on features, have encountered any bugs, or have suggestions for enhancements, we're eager to hear from you. Your insights help us make the analytics dashboard more robust and user-friendly. Ideas for data or visualisations you'd like to see, can be shared with us till **15th January 2026** for showcase at GA4GH Connect 2026. 

You can create an [issue](https://github.com/ga4gh/analytics-dashboard/issues) using one of the templates available. This will be reviewed and once approved, will be developed in a new branch. After the development and testing is completed, the branch (and the changes suggested through it) will be reviewed through a pull request (PR). PR will be reviewed and merged into `main`. All branches are deleted after merge. 

---

## 📃 License
Licensed under the Apache License, Version 2.0 (the "License").

---

## 🗨️ Contacts
If you'd like to get in touch with the primary maintainers - GA4GH tech team - you can contact them at the following email. 

- **Email**: Send us your inquiries or support requests at [ga4gh-tech-team@ga4gh.org](mailto:ga4gh-tech-team@ga4gh.org).

We look forward to assisting you and ensuring your experience with our product is successful and enjoyable!

[Back to top](#top)
