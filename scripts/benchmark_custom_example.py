"""
Example: Extending the benchmark with custom operations

This demonstrates how to add your own benchmark operations to the registry
without modifying the core benchmark_bottlenecks.py file.
"""

from benchmark_bottlenecks import (
    registry,
    BenchmarkRunner,
    create_flow_system,
    run_benchmark,
    print_summary,
    print_by_timesteps,
    print_by_components,
    print_detailed_results,
    save_results,
)


# ============================================================================
# Custom Operations - Simply add more decorated functions!
# ============================================================================

@registry.register(
    'sel_first_half',
    description='Select first half of timesteps using isel',
    requires_dataset=True
)
def benchmark_sel_first_half(flow_system, dataset):
    """Select first half of timesteps using integer indexing."""
    n_times = len(dataset.time)
    return lambda: dataset.isel(time=slice(0, n_times // 2))


@registry.register(
    'sel_last_quarter',
    description='Select last quarter of timesteps',
    requires_dataset=True
)
def benchmark_sel_last_quarter(flow_system, dataset):
    """Select last quarter of timesteps."""
    n_times = len(dataset.time)
    return lambda: dataset.isel(time=slice(3 * n_times // 4, n_times))


@registry.register(
    'resample_2h',
    description='Resample to 2-hour frequency',
    requires_dataset=True
)
def benchmark_resample_2h(flow_system, dataset):
    """Benchmark dataset resampling to 2h frequency."""
    return lambda: fx.FlowSystem._dataset_resample(dataset, '2h')


@registry.register(
    'dataset_copy',
    description='Copy the entire dataset',
    requires_dataset=True
)
def benchmark_dataset_copy(flow_system, dataset):
    """Benchmark deep copy of dataset."""
    return lambda: dataset.copy(deep=True)


@registry.register(
    'dataset_mean',
    description='Calculate mean across all variables',
    requires_dataset=True
)
def benchmark_dataset_mean(flow_system, dataset):
    """Calculate mean of all variables in dataset."""
    return lambda: dataset.mean()


# ============================================================================
# Custom Configuration
# ============================================================================

CUSTOM_CONFIG = {
    'timestep_sizes': [100, 1000, 5000],  # Test more sizes
    'component_counts': [5, 10],           # Test multiple component counts
    'n_runs': 3,                           # More runs for better averaging
}


if __name__ == '__main__':
    print("=" * 100)
    print("CUSTOM BENCHMARK EXAMPLE")
    print("=" * 100)
    print(f"\nAvailable operations: {', '.join(registry.list_operations())}\n")

    # Example 1: Run all operations
    print("\n" + "=" * 100)
    print("EXAMPLE 1: Running ALL operations (default + custom)")
    print("=" * 100)

    runner = BenchmarkRunner(registry)
    results_df = run_benchmark(CUSTOM_CONFIG, runner)
    operation_cols = list(registry.get_enabled_operations().keys())
    print_summary(results_df, operation_cols)

    # Example 2: Run only specific operations
    print("\n\n" + "=" * 100)
    print("EXAMPLE 2: Running ONLY custom selection operations")
    print("=" * 100)

    registry.enable_only(['sel_first_half', 'sel_last_quarter', 'sel'])
    runner2 = BenchmarkRunner(registry)
    results_df2 = run_benchmark(CUSTOM_CONFIG, runner2)
    operation_cols2 = list(registry.get_enabled_operations().keys())
    print_summary(results_df2, operation_cols2)

    # Example 3: Disable specific operations
    print("\n\n" + "=" * 100)
    print("EXAMPLE 3: Running all EXCEPT coarsen and mean operations")
    print("=" * 100)

    # First re-enable all
    for op in registry.list_operations():
        registry.enable_operation(op)

    # Then disable specific ones
    registry.disable_operation('coarsen')
    registry.disable_operation('dataset_mean')

    runner3 = BenchmarkRunner(registry)
    results_df3 = run_benchmark(CUSTOM_CONFIG, runner3)
    operation_cols3 = list(registry.get_enabled_operations().keys())
    print_detailed_results(results_df3, operation_cols3)

    print("\n" + "=" * 100)
    print("EXAMPLES COMPLETED")
    print("=" * 100)
