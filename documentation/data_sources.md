# PureFlow data sources

## Loaded dataset

The current database contains the transformed version of `data-center-water.csv` (dataset ID `1cced4863e37452db38f10683ed66961`): 85 source observations, 21 columns, and a mix of site volume, WUE, per-prompt, training, regional, and fleet-level records. The source file's `source_title` and `source_url` columns identify the materials below. The reporting system reads those provenance fields from the transformed file; they are not inferred from publisher names.

Representative sources as recorded in the dataset:

| Publisher / source in file | Source title recorded in file | Link |
| --- | --- | --- |
| Google | Google 2026 Environmental Report (FY2025), water use by data centre location | [Google report PDF](https://sustainability.google/files/google-2026-environmental-report.pdf) |
| Amazon Web Services | AWS Cloud region PUE and WUE table | [Amazon Sustainability](https://sustainability.aboutamazon.com/products-services/aws-cloud) |
| Microsoft | Datacenters: Efficiency (PUE and WUE by region) | [Microsoft Datacenters](https://datacenters.microsoft.com/sustainability/efficiency/) |
| Equinix | FY2025 Annual Report (SEC Form ARS) | [SEC filing](https://www.sec.gov/Archives/edgar/data/1101239/000110123926000075/EQIXAnnualRpt2025PRINT.pdf) |
| Digital Realty | 2025 Impact Report announcement | [Digital Realty source](https://mfn.se/all/a/digital-realty/digital-realty-publishes-2025-impact-report-highlighting-sustainability-progress-f0a795c9) |
| Meta | 2025 Environmental Data Index, water section | [Meta index](https://sustainability.atmeta.com/asset/2025-environmental-data-index) |
| European Commission | COM(2026) 500 final, section 2.2.2 | [EUR-Lex document](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:52026DC0500) |
| Elsworth et al. | Measuring the environmental impact of delivering AI at Google Scale | [arXiv:2508.15734](https://arxiv.org/abs/2508.15734) |
| Li, Yang, Islam, and Ren | Making AI Less Thirsty | [arXiv:2304.03271](https://arxiv.org/abs/2304.03271) |
| OpenAI | The Gentle Singularity | [Sam Altman source](https://blog.samaltman.com/the-gentle-singularity) |
| Mistral AI | Contribution to a global environmental standard for AI | [Mistral source](https://mistral.ai/news/our-contribution-to-a-global-environmental-standard-for-ai) |

Other rows cite AWS Sustainability and multiple distinct tables or sections from the same publisher. A report export includes the source titles and URLs it can read from the selected transformed files.

## Licensing and attribution

The dataset stores source titles and links but does not store a license field or a complete rights assessment. PureFlow therefore labels the license as **not specified in the project metadata**. The source URLs are provenance, not permission to redistribute source documents or reproduce their contents. Follow each publisher's terms and any applicable license before reuse. The uploaded CSV itself is user-provided project data; its original compilation license is not recorded.

## Caveats

This is a heterogeneous compiled dataset, not one publisher's uniform operational time series. Rows can describe a physical site, cloud region, company fleet, prompt estimate, study, or policy source. Country values are absent on 26 of 85 rows. A source title or publisher does not establish that two records share a definition, scope, time boundary, or assurance level.
