---
anta_title: ANTA catalog for security tests
---
<!--
  ~ Copyright (c) 2023-2025 Arista Networks, Inc.
  ~ Use of this source code is governed by the Apache License 2.0
  ~ that can be found in the LICENSE file.
  -->

# Tests

::: anta.tests.security

    options:
      show_root_heading: false
      show_root_toc_entry: false
      show_bases: false
      merge_init_into_class: false
      anta_hide_test_module_description: true
      show_labels: true
      filters:
        - "!test"
        - "!render"

# Input models

::: anta.input_models.security

    options:
      show_root_heading: false
      show_root_toc_entry: false
      show_bases: false
      merge_init_into_class: false
      anta_hide_test_module_description: true
      show_labels: true
      filters:
        - "!^__init__"
        - "!^__str__"
