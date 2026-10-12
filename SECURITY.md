# Security

Keep the API on loopback unless you deliberately configure authenticated network access. Upstream Strata supplies API authentication; Sprint retains its settings and rejects non-loopback startup without a key. For remote access, use your normal authenticated TLS ingress and firewall policy.

Runtime configs can contain access keys. Keep them outside the repository and limit filesystem access. Status files contain only health metadata; optional upstream request logging/monitoring has its own content-retention behavior.

For a sensitive report, use GitHub's private vulnerability reporting on this repository when available. Do not post credentials or private prompts in an issue. If the issue is in upstream Strata, follow its security policy too.

This software is provided under the MIT license without warranties. The current profile has finite validation on one hardware/model combination.
