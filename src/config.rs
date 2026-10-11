pub fn secret(name: &str) -> anyhow::Result<String> {
    if let Ok(path) = std::env::var(format!("{name}_FILE")) {
        let value = std::fs::read_to_string(path)
            .map_err(|_| anyhow::anyhow!("Cannot read {name}_FILE"))?;
        anyhow::ensure!(!value.trim().is_empty(), "Empty {name}_FILE");
        Ok(value.trim().to_owned())
    } else {
        Ok(std::env::var(name).map_err(|_| anyhow::anyhow!("Missing {name}"))?)
    }
}
