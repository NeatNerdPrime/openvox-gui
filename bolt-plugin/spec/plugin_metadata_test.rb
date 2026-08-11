# frozen_string_literal: true

require 'json'
require 'pathname'
require 'yaml'

ROOT = Pathname.new(__dir__).parent

module Assert
  module_function

  def assert(cond, msg = 'assertion failed')
    raise msg unless cond
  end

  def assert_equal(expected, actual, msg = nil)
    return if expected == actual

    raise(msg || "expected #{expected.inspect}, got #{actual.inspect}")
  end

  def assert_includes(collection, item, msg = nil)
    return if collection.include?(item)

    raise(msg || "expected #{collection.inspect} to include #{item.inspect}")
  end
end

class PluginMetadataTests
  extend Assert

  def self.run_all
    tests = public_methods(false).grep(/\Atest_/).sort
    failures = []
    tests.each do |name|
      begin
        send(name)
        puts "  OK  #{name}"
      rescue StandardError => e
        failures << [name, e]
        puts "  FAIL #{name}: #{e.message}"
      end
    end
    [tests.size, failures]
  end

  def self.test_bolt_plugin_json_hooks_resolve_reference
    data = JSON.parse(File.read(ROOT / 'openvox_enc' / 'bolt_plugin.json'))
    assert_equal 'openvox_enc', data['name']
    assert data.dig('hooks', 'resolve_reference', 'task')
    assert_equal 'openvox_enc::resolve_reference', data['hooks']['resolve_reference']['task']
  end

  def self.test_metadata_json_basic_fields
    data = JSON.parse(File.read(ROOT / 'openvox_enc' / 'metadata.json'))
    assert_equal 'openvox-openvox_enc', data['name']
    assert data['version']
    assert_equal 'Apache-2.0', data['license']
  end

  def self.test_resolve_reference_task_json_parameters
    data = JSON.parse(File.read(ROOT / 'openvox_enc' / 'tasks' / 'resolve_reference.json'))
    params = data['parameters']
    %w[api_url group transport ssl_verify api_token token_file run_as run_as_command].each do |key|
      assert params.key?(key), "missing parameter #{key}"
    end
    assert_equal 'https://localhost:4567', params['api_url']['default']
    assert_equal 'ssh', params['transport']['default']
    assert_equal false, params['ssl_verify']['default']
    assert_equal '/etc/puppetlabs/bolt/.bolt_token', params['token_file']['default']
  end

  def self.test_inventory_example_declares_openvox_enc_plugin
    text = File.read(ROOT / 'inventory.yaml.example')
    # YAML may be comment-heavy; ensure the plugin key is present
    assert_includes text, '_plugin: openvox_enc'
    assert_includes text, 'api_url:'
    data = YAML.safe_load(text)
    enc_group = data['groups'].find { |g| g['name'] == 'enc' }
    assert enc_group, 'enc group missing from inventory.yaml.example'
    targets = enc_group['targets']
    plugin = if targets.is_a?(Hash)
               targets
             else
               Array(targets).find { |t| t.is_a?(Hash) && t['_plugin'] == 'openvox_enc' }
             end
    assert plugin && plugin['_plugin'] == 'openvox_enc', 'openvox_enc plugin target missing'
  end

  def self.test_library_and_task_files_exist
    assert File.file?(ROOT / 'openvox_enc' / 'lib' / 'openvox_enc' / 'inventory.rb')
    assert File.file?(ROOT / 'openvox_enc' / 'tasks' / 'resolve_reference.rb')
    task = File.read(ROOT / 'openvox_enc' / 'tasks' / 'resolve_reference.rb')
    # Working singleton uses the self-contained 3.10.6 task (no require_relative).
    assert_includes task, 'Net::HTTP'
    assert !task.include?('require_relative'), 'task must not require_relative (Bolt copies it to /tmp)'
  end

  def self.test_task_is_self_contained
    task = File.read(ROOT / 'openvox_enc' / 'tasks' / 'resolve_reference.rb')
    assert_includes task, 'Net::HTTP.new'
    assert_includes task, '/api/enc/inventory/bolt'
  end
end

puts 'openvox_enc plugin metadata tests'
total, failures = PluginMetadataTests.run_all
puts
if failures.empty?
  puts "All #{total} tests passed."
  exit 0
else
  puts "#{failures.size}/#{total} failed:"
  failures.each { |name, err| puts "  - #{name}: #{err.message}" }
  exit 1
end
