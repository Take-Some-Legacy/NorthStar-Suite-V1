#[derive(Clone, Copy)]
pub struct ToolMetadata {
    pub internal_name: &'static str,
    pub original_filename: &'static str,
    pub file_description: &'static str,
    pub icon_path: Option<&'static str>,
}

pub const COMPANY_NAME: &str = "Take Some";
pub const ORGANIZATION: &str = "North Star";
pub const PRODUCT_NAME: &str = "North Star Toolbelt";
pub const LEGAL_COPYRIGHT: &str = "Copyright (c) Take Some / North Star contributors";
pub const LANGUAGE_EN_US: u16 = 0x0409;
