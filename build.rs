fn main() {
    // Stable Rust needs an explicit build dependency for embedded SQLx
    // migration directory changes; deployments must carry the actual SQL.
    println!("cargo:rerun-if-changed=migrations");
    println!("cargo:rerun-if-changed=data/contracts/openapi.json");
}
