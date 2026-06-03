fn main() {
    #[cfg(windows)]
    {
        let mut res = winres::WindowsResource::new();
        res.set("FileDescription", "North Star YDD NEF8 drawable dictionary importer");
        res.set("ProductName", "North Star Engine Tools");
        let _ = res.compile();
    }
}
