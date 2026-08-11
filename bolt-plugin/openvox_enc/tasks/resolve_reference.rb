#!/opt/puppetlabs/puppet/bin/ruby
# frozen_string_literal: true

###############################################################################
# OpenVox ENC Bolt Inventory Plugin — resolve_reference task
#
# Thin Bolt task entrypoint. All logic lives in
# openvox_enc/lib/openvox_enc/inventory.rb so it can be unit-tested without
# Bolt. When inventory.yaml has `_plugin: openvox_enc`, Bolt invokes this
# task with JSON on stdin and expects JSON on stdout.
###############################################################################

require 'json'

# Bolt copies this task to /tmp/<uuid>/resolve_reference.rb, so
# require_relative '../lib/...' looks at /tmp/lib and fails.
_lib_candidates = [
  File.expand_path('../../lib', __dir__),
  '/etc/puppetlabs/bolt/modules/openvox_enc/lib',
  '/opt/openvox-gui/bolt-plugin/openvox_enc/lib',
]
_lib_candidates.each do |lib|
  next unless lib && File.directory?(lib)

  $LOAD_PATH.unshift(lib) unless $LOAD_PATH.include?(lib)
end
require 'openvox_enc/inventory'

params = JSON.parse($stdin.read)
outcome = OpenvoxEnc::Inventory.resolve(params)

puts outcome[:payload].to_json
exit outcome[:exit_code]
