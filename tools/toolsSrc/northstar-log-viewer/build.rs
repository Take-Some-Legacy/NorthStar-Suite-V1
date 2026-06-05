fn main() {
    #[cfg(windows)]
    {
        let mut res = winres::WindowsResource::new();
        res.set("FileDescription", "North Star Log Viewer");
        res.set("ProductName", "North Star");
        let _ = res.compile();
    }
}
