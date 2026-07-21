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
require_relative '../lib/openvox_enc/inventory'

params = JSON.parse($stdin.read)
outcome = OpenvoxEnc::Inventory.resolve(params)

puts outcome[:payload].to_json
exit outcome[:exit_code]
