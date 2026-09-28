# Enable bundled demo inputs only in disposable integration-test builds.
# Production keeps its personal-site exclusions and blank comment credentials.
require "yaml"

config = YAML.unsafe_load_file("_config.yml")
override = {
  "exclude" => Array(config["exclude"]).reject do |path|
    %w[_posts _bibliography].include?(path.to_s.delete_suffix("/"))
  end,
  "disqus_shortname" => "al-folio-test",
  "giscus" => {
    "repo" => "alshedivat/al-folio",
    "repo_id" => "R_kgDOExample",
    "category" => "Comments",
    "category_id" => "DIC_kwDOExample"
  }
}
File.write(ARGV.fetch(0), override.to_yaml)
