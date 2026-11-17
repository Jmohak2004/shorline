// Compiles the lightwallet-protocol definitions with a pure-Rust protobuf
// compiler (protox), so building Shorline does not require `protoc`.
fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("cargo:rerun-if-changed=proto");
    let fds = protox::compile(["proto/service.proto"], ["proto"])?;
    tonic_build::configure()
        .build_server(false)
        .compile_fds(fds)?;
    Ok(())
}
