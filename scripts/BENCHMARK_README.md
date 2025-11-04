# Benchmark Pattern Documentation

## Overview

The benchmark system uses a **decorator-based registry pattern** to make it easy to add, configure, and run different benchmark operations without rewriting core logic.

## Key Design Patterns

### 1. Registry Pattern
A central `BenchmarkRegistry` stores all available benchmark operations. Operations can be easily enabled/disabled without modifying code.

### 2. Decorator Pattern
Use the `@registry.register()` decorator to add new benchmark operations. No need to modify the core runner code.

### 3. Strategy Pattern
Each benchmark operation is a separate strategy that can be executed by the runner.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    BenchmarkRegistry                         │
│  - Stores all operations                                     │
│  - Enable/disable operations                                 │
│  - Provides decorator for registration                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ uses
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    BenchmarkRunner                           │
│  - Executes enabled operations                               │
│  - Manages dataset creation                                  │
│  - Collects timing results                                   │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ executes
                            ▼
┌─────────────────────────────────────────────────────────────┐
│               Registered Operations                          │
│  @registry.register() decorated functions                    │
│  - to_dataset, from_dataset, sel, resample, etc.            │
└─────────────────────────────────────────────────────────────┘
```

## How to Add New Operations

### Basic Example

```python
@registry.register(
    'my_operation',
    description='What this operation does',
    requires_dataset=True  # Set to False if operation doesn't need dataset
)
def benchmark_my_operation(flow_system, dataset):
    """
    Benchmark a custom operation.

    Args:
        flow_system: The FlowSystem being benchmarked
        dataset: Pre-computed xarray dataset (None if requires_dataset=False)

    Returns:
        A callable (lambda or function) that performs the operation
    """
    return lambda: dataset.some_operation()
```

### Parameters Explained

- **name** (str): Unique identifier for the operation. Used in results and configuration.
- **description** (str): Human-readable description of what the operation does.
- **requires_dataset** (bool):
  - `True`: Operation needs a pre-computed dataset (e.g., for dataset operations like sel, resample)
  - `False`: Operation works directly with FlowSystem (e.g., to_dataset conversion)
- **enabled** (bool): Whether the operation is enabled by default.

## Usage Examples

### Example 1: Run All Default Operations

```python
from benchmark_bottlenecks import registry, BenchmarkRunner, run_benchmark, CONFIG

runner = BenchmarkRunner(registry)
results = run_benchmark(CONFIG, runner)
```

### Example 2: Run Only Specific Operations

```python
# Enable only selection and resampling operations
registry.enable_only(['sel', 'resample', 'resample_2h'])

runner = BenchmarkRunner(registry)
results = run_benchmark(CONFIG, runner)
```

### Example 3: Disable Specific Operations

```python
# Run all except coarsen
registry.disable_operation('coarsen')

runner = BenchmarkRunner(registry)
results = run_benchmark(CONFIG, runner)
```

### Example 4: Add Custom Operations

```python
# Add a new operation
@registry.register('sel_every_10th', description='Select every 10th timestep', requires_dataset=True)
def benchmark_sel_sparse(flow_system, dataset):
    return lambda: dataset.isel(time=slice(None, None, 10))

# Now run benchmark with your custom operation included
runner = BenchmarkRunner(registry)
results = run_benchmark(CONFIG, runner)
```

## Configuration

Modify the `CONFIG` dictionary to change benchmark parameters:

```python
CONFIG = {
    'timestep_sizes': [100, 1000, 5000],  # Number of timesteps to test
    'component_counts': [5, 10, 20],      # Number of components to test
    'n_runs': 3,                          # Timing iterations per configuration
}
```

## Output

The benchmark produces:

1. **Console output**:
   - Summary statistics
   - Scaling by timesteps
   - Scaling by components
   - Detailed results table

2. **CSV file**: `benchmark_results.csv` - All raw timing data

3. **NetCDF file**: `benchmark_results.nc` - Multidimensional structure for analysis with xarray

## Advanced: Creating a Separate Benchmark Suite

You can create a completely separate benchmark file that imports and extends the registry:

```python
# my_custom_benchmarks.py
from benchmark_bottlenecks import registry, BenchmarkRunner

# Add custom operations
@registry.register('my_op_1', description='Custom operation 1', requires_dataset=True)
def my_op_1(flow_system, dataset):
    return lambda: dataset.custom_method()

@registry.register('my_op_2', description='Custom operation 2', requires_dataset=False)
def my_op_2(flow_system, dataset):
    return lambda: flow_system.custom_method()

# Run with only your operations
registry.enable_only(['my_op_1', 'my_op_2'])
runner = BenchmarkRunner(registry)
results = run_benchmark(CONFIG, runner)
```

## Benefits of This Pattern

1. **Extensibility**: Add new operations with a simple decorator - no core code changes
2. **Flexibility**: Easily enable/disable operations for different benchmark scenarios
3. **Maintainability**: Each operation is self-contained and documented
4. **Reusability**: Share operations across different benchmark configurations
5. **Clarity**: Clear separation between operation definition, execution, and reporting
6. **Type Safety**: Dataclass-based operation representation
7. **DRY Principle**: No code duplication when adding new operations

## Real-World Use Cases

### Use Case 1: Compare Selection Methods
```python
registry.enable_only(['sel', 'sel_first_half', 'sel_last_quarter'])
```

### Use Case 2: Test Different Resample Frequencies
```python
# Add multiple resample operations with different frequencies
for freq in ['2h', '4h', '8h', '12h']:
    @registry.register(f'resample_{freq}', requires_dataset=True)
    def make_resample(frequency=freq):
        def inner(flow_system, dataset):
            return lambda: fx.FlowSystem._dataset_resample(dataset, frequency)
        return inner
```

### Use Case 3: Benchmark Data Export Formats
```python
@registry.register('export_csv', requires_dataset=True)
def benchmark_to_csv(flow_system, dataset):
    return lambda: dataset.to_dataframe().to_csv('/tmp/test.csv')

@registry.register('export_netcdf', requires_dataset=True)
def benchmark_to_netcdf(flow_system, dataset):
    return lambda: dataset.to_netcdf('/tmp/test.nc')
```

## Best Practices

1. **Naming**: Use descriptive operation names that indicate what's being tested
2. **Documentation**: Always add a docstring to your operation function
3. **Isolation**: Each operation should be independent and not modify shared state
4. **Return Callables**: Always return a lambda or function, not the result itself
5. **Resource Cleanup**: If your operation creates files/resources, clean them up in the callable

## Files

- `benchmark_bottlenecks.py` - Core benchmark implementation with default operations
- `benchmark_custom_example.py` - Example of extending with custom operations
- `BENCHMARK_README.md` - This documentation file
