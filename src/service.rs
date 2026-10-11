//! Service boundaries for the modular monolith's network deployment.
//!
//! The handlers and their public contract are intentionally shared while the
//! processes are isolated by domain.  This is a compatibility-first migration:
//! it permits independent scaling/failure containment without rewriting domain
//! rules or moving data during the same release.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Service {
    All,
    Gateway,
    Platform,
    Identity,
    Talent,
    Recruitment,
    Documents,
    Integrations,
    Intelligence,
}

impl Service {
    pub fn from_env() -> anyhow::Result<Self> {
        match std::env::var("FSP_SERVICE")
            .unwrap_or_else(|_| "all".into())
            .to_ascii_lowercase()
            .as_str()
        {
            "all" => Ok(Self::All),
            "gateway" => Ok(Self::Gateway),
            "platform" => Ok(Self::Platform),
            "identity" => Ok(Self::Identity),
            "talent" => Ok(Self::Talent),
            "recruitment" => Ok(Self::Recruitment),
            "documents" => Ok(Self::Documents),
            "integrations" => Ok(Self::Integrations),
            "intelligence" => Ok(Self::Intelligence),
            value => anyhow::bail!(
                "Unknown FSP_SERVICE={value}; expected all, gateway, platform, identity, talent, recruitment, documents or integrations"
            ),
        }
    }

    pub fn includes(self, domain: Self) -> bool {
        self == Self::All || self == domain
    }
    pub fn is_gateway(self) -> bool {
        self == Self::Gateway
    }
    pub fn serves_ui(self) -> bool {
        self == Self::All
    }
    pub fn runs_maintenance(self) -> bool {
        self.includes(Self::Platform)
    }
    pub fn runs_mail(self) -> bool {
        self.includes(Self::Platform)
    }
    pub fn runs_talantix_dispatch(self) -> bool {
        self.includes(Self::Integrations)
    }
    pub fn database_pool_limit(self) -> u32 {
        std::env::var("DATABASE_MAX_CONNECTIONS")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(if self == Self::All { 16 } else { 4 })
    }
}
