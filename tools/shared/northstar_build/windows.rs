use super::metadata::{ToolMetadata, COMPANY_NAME, LANGUAGE_EN_US, LEGAL_COPYRIGHT, ORGANIZATION, PRODUCT_NAME};

pub fn compile_windows_file_info(metadata: ToolMetadata) {
    #[cfg(target_os = "windows")]
    {
        let version = env!("CARGO_PKG_VERSION");
        let mut resource = winres::WindowsResource::new();

        if let Some(icon_path) = metadata.icon_path {
            println!("cargo:rerun-if-changed={icon_path}");
            resource.set_icon(icon_path);
        }

        resource.set("CompanyName", COMPANY_NAME);
        resource.set("Organization", ORGANIZATION);
        resource.set("FileDescription", metadata.file_description);
        resource.set("FileVersion", version);
        resource.set("InternalName", metadata.internal_name);
        resource.set("LegalCopyright", LEGAL_COPYRIGHT);
        resource.set("OriginalFilename", metadata.original_filename);
        resource.set("ProductName", PRODUCT_NAME);
        resource.set("ProductVersion", version);
        resource.set_language(LANGUAGE_EN_US);

        if let Err(err) = resource.compile() {
            panic!("failed to compile Windows resources for {}: {err}", metadata.internal_name);
        }
    }

    #[cfg(not(target_os = "windows"))]
    {
        let _ = metadata;
    }
}
