#[cfg(target_os = "windows")]
fn main() {
    let version = env!("CARGO_PKG_VERSION");
    let mut resource = winres::WindowsResource::new();
    resource.set("CompanyName", "Take Some");
    resource.set("FileDescription", "North Star YTYP Packer");
    resource.set("FileVersion", version);
    resource.set("InternalName", "northstar-ytyp-packer");
    resource.set("LegalCopyright", "Copyright (c) Take Some");
    resource.set("OriginalFilename", "northstar-ytyp-packer.exe");
    resource.set("ProductName", "North Star Engine");
    resource.set("ProductVersion", version);
    resource.set_language(0x0409);
    if let Err(err) = resource.compile() {
        panic!("failed to compile Windows FileInfo resource for northstar-ytyp-packer: {err}");
    }
}

#[cfg(not(target_os = "windows"))]
fn main() {}
